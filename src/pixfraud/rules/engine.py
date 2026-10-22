"""Motor de regras determinístico, versionado em YAML.

Contrato de segurança (fail-safe): qualquer erro do motor (feature ausente, operador desconhecido, regra
malformada) resulta em decisão ``REVIEW`` com reason code ``ENGINE_ERROR`` — nunca em ``APPROVE`` silencioso.
"""

from __future__ import annotations

import copy
import operator
from dataclasses import dataclass, field
from functools import reduce
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

ACTION_RANK = {"APPROVE": 0, "REVIEW": 1, "BLOCK": 2}
_RANK_ACTION = {v: k for k, v in ACTION_RANK.items()}
_OPS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt, "==": operator.eq, "!=": operator.ne}
DEFAULT_RULES = Path(__file__).with_name("rules_v1.yaml")


class RuleEngineError(Exception):
    """Falha de definição ou de avaliação de regra."""


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    action: str
    weight: float
    reason_code: str
    when: dict
    params: dict = field(default_factory=dict)

    def features(self) -> set[str]:
        return _features_used(self.when)


def _features_used(node: dict) -> set[str]:
    if "all" in node:
        return set().union(*[_features_used(n) for n in node["all"]]) if node["all"] else set()
    if "any" in node:
        return set().union(*[_features_used(n) for n in node["any"]]) if node["any"] else set()
    return {node["feature"]}


def _resolve(value: Any, params: dict) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        key = value[1:]
        if key not in params:
            raise RuleEngineError(f"parâmetro não definido: {key}")
        return params[key]
    return value


def _mask(node: dict, df: pd.DataFrame, params: dict) -> pd.Series:
    if "all" in node:
        return reduce(lambda a, b: a & b, [_mask(n, df, params) for n in node["all"]])
    if "any" in node:
        return reduce(lambda a, b: a | b, [_mask(n, df, params) for n in node["any"]])
    try:
        feat, op, raw = node["feature"], node["op"], node["value"]
    except KeyError as exc:
        raise RuleEngineError(f"condição malformada: {node}") from exc
    if feat not in df.columns:
        raise RuleEngineError(f"feature ausente: {feat}")
    val = _resolve(raw, params)
    col = df[feat]
    if op == "in":
        res = col.isin(list(val))
    elif op in _OPS:
        res = _OPS[op](col, val)
    else:
        raise RuleEngineError(f"operador desconhecido: {op}")
    return res.fillna(False).astype(bool)


@dataclass
class RuleResult:
    decisions: pd.DataFrame  # tx_id, decision, rule_score, rules_hit, reason_codes, evidence
    hits: pd.DataFrame  # uma coluna booleana por regra, mesmo índice de entrada


class RuleSet:
    def __init__(self, version: str, rules: list[Rule]):
        ids = [r.id for r in rules]
        if len(ids) != len(set(ids)):
            raise RuleEngineError("IDs de regra duplicados")
        self.version = version
        self.rules = rules

    @classmethod
    def load(cls, path: str | Path | None = None) -> "RuleSet":
        raw = yaml.safe_load(Path(path or DEFAULT_RULES).read_text(encoding="utf-8"))
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "RuleSet":
        if not isinstance(raw, dict) or "rules" not in raw or "version" not in raw:
            raise RuleEngineError("YAML precisa de 'version' e 'rules'")
        rules = []
        for item in raw["rules"]:
            for key in ("id", "name", "action", "weight", "reason_code", "when"):
                if key not in item:
                    raise RuleEngineError(f"regra {item.get('id', '?')} sem campo '{key}'")
            if item["action"] not in ("REVIEW", "BLOCK"):
                raise RuleEngineError(f"ação inválida em {item['id']}: {item['action']}")
            if not 0 <= float(item["weight"]) <= 1:
                raise RuleEngineError(f"peso fora de [0,1] em {item['id']}")
            rules.append(
                Rule(item["id"], item["name"], item["action"], float(item["weight"]), item["reason_code"],
                     item["when"], dict(item.get("params") or {}))
            )
        return cls(str(raw["version"]), rules)

    def get(self, rule_id: str) -> Rule:
        for r in self.rules:
            if r.id == rule_id:
                return r
        raise RuleEngineError(f"regra inexistente: {rule_id}")

    def with_params(self, overrides: dict[str, dict[str, Any]]) -> "RuleSet":
        """Cópia com parâmetros alterados (varredura de limiar). Não muda o YAML em disco."""
        new = copy.deepcopy(self.rules)
        for rid, upd in overrides.items():
            idx = next((i for i, r in enumerate(new) if r.id == rid), None)
            if idx is None:
                raise RuleEngineError(f"regra inexistente: {rid}")
            for k in upd:
                if k not in new[idx].params:
                    raise RuleEngineError(f"{rid} não tem o parâmetro {k}")
            new[idx] = Rule(**{**new[idx].__dict__, "params": {**new[idx].params, **upd}})
        return RuleSet(self.version, new)

    def evaluate(self, df: pd.DataFrame) -> RuleResult:
        hits = pd.DataFrame({r.id: _mask(r.when, df, r.params) for r in self.rules}, index=df.index)
        h = hits.to_numpy()
        rank = np.zeros(len(df), dtype=int)
        keep = np.ones(len(df), dtype=float)
        for j, r in enumerate(self.rules):
            rank = np.where(h[:, j], np.maximum(rank, ACTION_RANK[r.action]), rank)
            keep = keep * np.where(h[:, j], 1 - r.weight, 1.0)
        rule_ids = np.array([r.id for r in self.rules])
        reason = {r.id: r.reason_code for r in self.rules}
        feats = {r.id: sorted(r.features()) for r in self.rules}
        reasons, hit_lists, evidence = [], [], []
        for i in range(len(df)):
            ids = list(rule_ids[h[i]])
            hit_lists.append(ids)
            reasons.append([reason[x] for x in ids])
            ev = {}
            for x in ids:
                for f in feats[x]:
                    v = df[f].iat[i]
                    ev[f] = v.item() if hasattr(v, "item") else v
            evidence.append(ev)
        out = pd.DataFrame(
            {
                "tx_id": df["tx_id"].to_numpy() if "tx_id" in df.columns else df.index,
                "decision": [_RANK_ACTION[x] for x in rank],
                "rule_score": 1 - keep,
                "rules_hit": hit_lists,
                "reason_codes": reasons,
                "evidence": evidence,
            },
            index=df.index,
        )
        return RuleResult(out, hits)


def safe_decide(ruleset: RuleSet, df: pd.DataFrame) -> RuleResult:
    """Avalia com fail-safe: qualquer exceção vira REVIEW/ENGINE_ERROR para todas as linhas."""
    try:
        return ruleset.evaluate(df)
    except Exception as exc:  # noqa: BLE001 — o contrato é justamente não deixar nada passar
        out = pd.DataFrame(
            {
                "tx_id": df["tx_id"].to_numpy() if "tx_id" in df.columns else df.index,
                "decision": "REVIEW",
                "rule_score": 0.5,
                "rules_hit": [["ENGINE_ERROR"]] * len(df),
                "reason_codes": [["ENGINE_ERROR"]] * len(df),
                "evidence": [{"error": f"{type(exc).__name__}: {exc}"}] * len(df),
            },
            index=df.index,
        )
        return RuleResult(out, pd.DataFrame(index=df.index))
