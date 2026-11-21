"""Explicit correction of an unexecuted tool candidate; no business writes.

The ToolLoop owns the live record and Conversation.context owns its durable
exchange. This module supplies only identity, diagnostics and bounded merge
mechanics. A successful merge is still validated and executed as the original
tool, never saved here.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel, model_validator

from app.agents.arguments import resolve_error_path, schema_at_path

CORRECTION_TOOL_NAME = "correct_tool_candidate"
_IDENTITY_KEYS = (
    "op", "scene_id", "track_id", "clip_id", "object_id", "animation_id",
    "snapshot_id", "kind", "at", "id",
)



class CandidateScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)


class CandidateCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_id: str = Field(min_length=1, max_length=80)
    value: JsonValue = Field(
        default=None,
        description="对应该诊断的新 JSON 值。null 是有效值。operation=remove 时传 null 或省略，operation=move 时传入确切的已声明目标标记。"
    )


class PatchCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    candidate_digest: str = Field(min_length=64, max_length=64)
    mode: Literal["patch"]
    corrections: list[CandidateCorrection] = Field(
        min_length=1,
        description="只提交当前的 error_id。服务端保留其他字段和数组位置。",
    )


class ReplaceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1)
    candidate_digest: str = Field(min_length=64, max_length=64)
    mode: Literal["replace"]
    reason: str = Field(min_length=1, max_length=1000)
    arguments: dict[str, JsonValue] = Field(
        description="原目标工具的完整新参数。旧字段不会合入此次替换。"
    )


class CandidateCorrectionArgs(RootModel[
    Annotated[PatchCandidate | ReplaceCandidate, Field(discriminator="mode")]
]):
    """The wire's patch/replace discriminated union; mixed forms do not validate."""

    @model_validator(mode="before")
    @classmethod
    def _corrections_item_dialect(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("mode") != "patch":
            return data
        corrections = data.get("corrections")
        if isinstance(corrections, dict) and set(corrections) == {"item"}:
            return {**data, "corrections": corrections["item"]}
        return data


class CorrectionError(ValueError):
    def __init__(self, code: str, message: str, *, error_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.error_id = error_id


@dataclass(frozen=True)
class CandidateRejected:
    """Execution-side content validation failed before any version was saved."""

    reason: str
    errors: list[dict]


@dataclass(frozen=True)
class RestoredCandidate:
    candidate_id: str
    candidate_digest: str
    tool_name: str
    arguments: dict
    errors: list[dict]
    base_keys: frozenset[str]
    call_id: str


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def tool_progress_digest(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    base_keys=(),
) -> str:
    """Content-only retry identity for retained tool calls."""
    encoded = json.dumps(
        {
            "target_tool": tool_name,
            "arguments": arguments,
            "base_keys": sorted(base_keys),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def candidate_progress_digest(record: CandidateRecord) -> str:
    """Random candidate ids never fake progress."""
    return tool_progress_digest(
        record.tool_name, record.arguments, base_keys=record.base_keys
    )


def _digest(*, candidate_id: str, scope: CandidateScope, tool_name: str, arguments: dict, base_keys: frozenset[str]) -> str:
    return hashlib.sha256(_canonical({
        "candidate_id": candidate_id,
        "owner_id": scope.owner_id,
        "conversation_id": scope.conversation_id,
        "target_tool": tool_name,
        "arguments": arguments,
        "base_keys": sorted(base_keys),
    }).encode("utf-8")).hexdigest()


def _value_at(value: Any, path: tuple) -> Any:
    cursor = value
    for key in path:
        if isinstance(cursor, dict) and key in cursor:
            cursor = cursor[key]
        elif isinstance(cursor, list) and isinstance(key, int) and 0 <= key < len(cursor):
            cursor = cursor[key]
        else:
            return None
    return cursor


def _model_path(path: tuple) -> str:
    text = ""
    for key in path:
        text += f"[{key}]" if isinstance(key, int) else ("." if text else "") + str(key)
    return text or "<arguments>"


def _pointer(path: tuple) -> str:
    return "".join("/" + str(key).replace("~", "~0").replace("/", "~1") for key in path) or ""


def _entities(arguments: dict, path: tuple) -> dict:
    found: dict[str, Any] = {}
    for depth in range(len(path) + 1):
        value = _value_at(arguments, path[:depth])
        if not isinstance(value, dict):
            continue
        for key in _IDENTITY_KEYS:
            if key in value and isinstance(value[key], (str, int)):
                found[key] = value[key]
        clip = value.get("clip")
        if isinstance(clip, dict):
            if isinstance(clip.get("clip_id"), str):
                found["clip_id"] = clip["clip_id"]
            if isinstance(clip.get("scene_id"), str):
                found["scene_id"] = clip["scene_id"]
            obj = clip.get("object")
            if isinstance(obj, dict) and isinstance(obj.get("object_id"), str):
                found["object_id"] = obj["object_id"]
    return found


def _related_excerpt(arguments: dict, path: tuple) -> Any:
    if not path:
        return None
    parent = _value_at(arguments, path[:-1])
    if isinstance(parent, dict):
        excerpt = deepcopy(parent)
        # The complete candidate already carries large structured payloads.
        # Keep their identity/shape here rather than printing a second copy.
        for key, value in list(excerpt.items()):
            encoded = _canonical(value)
            if len(encoded) > 3000:
                excerpt[key] = {
                    "retained_in_candidate": True,
                    "kind": "array" if isinstance(value, list) else "object",
                    "length": len(value),
                }
        return excerpt
    return _value_at(arguments, path)


def _move_target(arguments: dict, schema: dict, path: tuple) -> tuple[str, tuple] | None:
    if len(path) < 2 or not isinstance(path[-1], str):
        return None
    parent_path, key = path[:-1], path[-1]
    parent = _value_at(arguments, parent_path)
    if not isinstance(parent, dict):
        return None
    parent_schema = schema_at_path(arguments, parent_path, schema)
    if not isinstance(parent_schema, dict):
        return None
    for child_name, child_schema in parent_schema.get("properties", {}).items():
        if child_name == key:
            continue
        child = parent.get(child_name)
        if not isinstance(child, dict) or key in child:
            continue
        child_schema = schema_at_path(arguments, (*parent_path, child_name), schema)
        if not isinstance(child_schema, dict) or key not in child_schema.get("properties", {}):
            continue
        # The actual Clip/Animation ownership rule, rather than an arbitrary
        # JSON destination: add_clip.animations -> add_clip.clip.animations.
        if key == "animations" and child_name != "clip":
            continue
        return f"{child_name}.{key}", (*parent_path, child_name, key)
    return None


def _related_operations(arguments: dict, entity: dict) -> list[dict]:
    edits = arguments.get("edits")
    if not isinstance(edits, list) or not entity:
        return []
    wanted = {key: {str(v) for v in value} if isinstance(value, list) else {str(value)}
              for key, value in entity.items() if isinstance(value, (str, int, list))}
    related = []
    for index, op in enumerate(edits):
        if not isinstance(op, dict):
            continue
        clip = op.get("clip") if isinstance(op.get("clip"), dict) else {}
        obj = clip.get("object") if isinstance(clip.get("object"), dict) else {}
        track = op.get("track") if isinstance(op.get("track"), dict) else {}
        scene = op.get("scene") if isinstance(op.get("scene"), dict) else {}
        identities = {
            "op": op.get("op"), "track_id": op.get("track_id") or track.get("track_id"),
            "scene_id": op.get("scene_id") or clip.get("scene_id") or scene.get("scene_id"),
            "clip_id": op.get("clip_id") or clip.get("clip_id"),
            "object_id": obj.get("object_id"),
        }
        animations = clip.get("animations") if isinstance(clip.get("animations"), list) else []
        animation_ids = [a.get("animation_id") for a in animations if isinstance(a, dict)]
        matched = any(
            key in wanted and (str(value) in wanted[key] if value is not None else False)
            for key, value in identities.items()
        ) or any(str(item) in wanted.get("animation_id", set()) for item in animation_ids)
        if matched:
            related.append({
                "edit_index": index, "path": ["edits", index],
                **{key: value for key, value in identities.items() if value is not None},
                "range": clip.get("range") or scene.get("range") or op.get("range"),
            })
    return related[:8]


def _schema_contract(node: dict, root: dict) -> dict:
    """Self-contained schema fragment, including only reachable definitions."""
    result = deepcopy(node)
    definitions = root.get("$defs", {})
    reached = {}
    def visit(value):
        if isinstance(value, dict):
            ref = value.get("$ref", "")
            if ref.startswith("#/$defs/"):
                key = ref.removeprefix("#/$defs/")
                if key not in reached and key in definitions:
                    reached[key] = deepcopy(definitions[key])
                    visit(reached[key])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(result)
    if reached:
        result["$defs"] = reached
    return result


def _wrapper_rule(record, path, schema_node):
    """Only group declared extra siblings into a missing required object."""
    if not path or schema_node.get("type") != "object":
        return None
    parent = _value_at(record.arguments, path[:-1])
    if not isinstance(parent, dict) or path[-1] in parent:
        return None
    extra_paths = {resolve_error_path(record.arguments, e.get("loc", ()), record.schema)
                   for e in record.errors if e.get("type") == "extra_forbidden"}
    fields = [key for key in schema_node.get("properties", {})
              if (*path[:-1], key) in extra_paths]
    if not fields or not set(schema_node.get("required", ())).issubset(fields):
        return None
    return {"operation": "wrap", "path": list(path), "source_fields": fields,
            "target_token": path[-1], "value": path[-1]}


def _diagnostic_errors(record: "CandidateRecord") -> list[dict]:
    diagnostics = []
    wrappers = {}
    covered = set()
    for error in record.errors:
        if error.get("type") != "missing":
            continue
        path = resolve_error_path(record.arguments, error.get("loc", ()), record.schema)
        rule = _wrapper_rule(record, path, schema_at_path(record.arguments, path, record.schema))
        if rule:
            wrappers[path] = rule
            covered.update((*path[:-1], key) for key in rule["source_fields"])
    for index, error in enumerate(record.errors):
        location = error.get("loc") or ()
        operation_path = error.get("operation_path")
        authored_path = operation_path or error.get("field_path")
        entity = error.get("entity") or {}
        clip_id = entity.get("clip_id")
        if not location and authored_path and clip_id:
            # Domain validators name entities; only a unique authored add can
            # become a patch path. Updates/ambiguous identity retain replace.
            matches = [i for i, op in enumerate(record.arguments.get("edits", []))
                       if isinstance(op, dict) and op.get("op") == "add_clip"
                       and isinstance(op.get("clip"), dict)
                       and op["clip"].get("clip_id") == clip_id]
            if len(matches) == 1:
                prefix = ("edits", matches[0])
                if operation_path:
                    location = (*prefix, *operation_path)
                else:
                    location = (*prefix, "clip", *authored_path)
        path = resolve_error_path(record.arguments, location, record.schema)
        if path in covered:
            continue
        schema_node = schema_at_path(record.arguments, path, record.schema) if path else {}
        actual = _value_at(record.arguments, path)
        entity = dict(error.get("entity") or _entities(record.arguments, path))
        correction: dict[str, Any] = {"operation": None}
        if path in wrappers:
            correction = wrappers[path]
        elif path and error.get("type") == "extra_forbidden":
            if isinstance(actual, (dict, list)) and actual:
                target = _move_target(record.arguments, record.schema, path)
                if target is not None:
                    token, destination = target
                    correction = {
                        "operation": "move", "target_token": token,
                        "source_path": list(path), "destination_path": list(destination),
                        "value": token,
                    }
                else:
                    correction["reason"] = "此结构化值没有获准的局部写入位置。通过显式 replace 保留它，服务端不会丢弃。"
            else:
                correction = {"operation": "remove", "path": list(path), "value": None}
        elif path:
            correction = {"operation": "set", "path": list(path), "value": "此确切路径允许的任意 JSON 值；结构允许时可为 null"}
        else:
            correction["reason"] = "此诊断没有唯一获准的局部路径。使用显式 replace 和完整新参数，自行保留无关内容。"
        diagnostics.append({
            "error_id": f"error_{index + 1}",
            "type": error.get("type", "value_error"),
            "relation": error.get("relation"),
            "message": error.get("msg", "invalid candidate"),
            "original_loc": list(location),
            "model_path": _model_path(path),
            "server_path": list(path),
            "json_pointer": _pointer(path),
            "original_value": actual if path else error.get("input"),
            "schema": _schema_contract(schema_node, record.schema),
            "entity": entity,
            "related_excerpt": _related_excerpt(record.arguments, path),
            "related_operations": _related_operations(record.arguments, entity),
            "correction": correction,
        })
    return diagnostics


@dataclass
class CandidateRecord:
    candidate_id: str
    candidate_digest: str
    tool_name: str
    arguments: dict
    errors: list[dict]
    schema: dict
    scope: CandidateScope
    base_keys: frozenset[str]
    call_id: str

    @classmethod
    def create(cls, *, tool_name: str, arguments: dict, errors: list[dict], schema: dict,
               scope: CandidateScope, base_keys: frozenset[str], call_id: str,
               candidate_id: str | None = None) -> "CandidateRecord":
        identity = candidate_id or f"cnd_{uuid4().hex}"
        return cls(identity, _digest(candidate_id=identity, scope=scope, tool_name=tool_name, arguments=arguments, base_keys=base_keys),
                   tool_name, deepcopy(arguments), deepcopy(errors), schema, scope, base_keys, call_id)

    @classmethod
    def restore(cls, restored: RestoredCandidate, *, schema: dict, scope: CandidateScope) -> "CandidateRecord":
        record = cls.create(tool_name=restored.tool_name, arguments=restored.arguments,
            errors=restored.errors, schema=schema, scope=scope, base_keys=restored.base_keys,
            call_id=restored.call_id, candidate_id=restored.candidate_id)
        if not hmac.compare_digest(record.candidate_digest, restored.candidate_digest):
            raise CorrectionError("candidate_digest", "Restored candidate identity does not match its retained arguments.")
        return record

    def verify(self, request: PatchCandidate | ReplaceCandidate) -> None:
        if request.candidate_id != self.candidate_id:
            raise CorrectionError("unknown_candidate", "candidate_id does not name a current retained candidate in this conversation.")
        expected = _digest(candidate_id=self.candidate_id, scope=self.scope,
                           tool_name=self.tool_name, arguments=self.arguments, base_keys=self.base_keys)
        if not hmac.compare_digest(request.candidate_digest, expected) or not hmac.compare_digest(self.candidate_digest, expected):
            raise CorrectionError("stale_candidate", "candidate_digest is stale or invalid. Read the latest diagnostic and correct only its current candidate.")

    def updated(self, arguments: dict, errors: list[dict], *, call_id: str) -> "CandidateRecord":
        return CandidateRecord.create(tool_name=self.tool_name, arguments=arguments, errors=errors,
            schema=self.schema, scope=self.scope, base_keys=self.base_keys, call_id=call_id,
            candidate_id=self.candidate_id)

    def diagnostic(self, *, include_candidate: bool = False, kind: str = "params_validation",
                   correction_error: CorrectionError | None = None) -> dict:
        payload = {
            "ok": False,
            "execution": "not executed",
            "saved": False,
            "kind": kind,
            "candidate_id": self.candidate_id,
            "candidate_digest": self.candidate_digest,
            "target_tool": self.tool_name,
            "candidate_location": "this tool result's candidate field" if include_candidate else f"retained assistant tool_call {self.call_id} arguments",
            "candidate_authority": "只有此组 candidate_id 和 candidate_digest 有效，旧摘要已过期。",
            "correction_tool": CORRECTION_TOOL_NAME,
            "correction_contract": {
                "patch": "只返回当前的 error_id/value 修正。服务端保留未涉及的内容，不要重复候选或目标工具名。",
                "replace": "显式选择 mode=replace，并提供原因和完整新参数。结构修改不会自动触发 replace。",
                "result": "合并后会校验完整候选，只有原目标工具返回保存成功时才算已保存。",
            },
            "target_parameters_schema": deepcopy(self.schema),
            "path_contract": "model_path、server_path、json_pointer 是实际 JSON 路径。original_loc 表明校验错误位置，其中的联合类型标记不是 JSON 键。",
            "errors": _diagnostic_errors(self),
        }
        if include_candidate:
            payload["candidate"] = deepcopy(self.arguments)
        if correction_error is not None:
            payload["correction_error"] = {
                "code": correction_error.code, "message": str(correction_error),
                "error_id": correction_error.error_id,
            }
        return payload


@dataclass(frozen=True)
class CorrectionMerge:
    arguments: dict
    mode: str
    reason: str | None
    complete_arguments_in_call: bool


def _paths_overlap(left: tuple, right: tuple) -> bool:
    return left[:len(right)] == right or right[:len(left)] == left


def _set_at(value: Any, path: tuple, replacement: Any) -> None:
    if not path:
        raise CorrectionError("scope_required", "The candidate root cannot be replaced by patch; use explicit replace.")
    parent = _value_at(value, path[:-1])
    key = path[-1]
    if isinstance(parent, dict):
        parent[key] = deepcopy(replacement)
    elif isinstance(parent, list) and isinstance(key, int) and 0 <= key < len(parent):
        parent[key] = deepcopy(replacement)
    else:
        raise CorrectionError("scope_required", "The parent of this diagnostic no longer exists; use the latest diagnostic or explicit replace.")


def _remove_at(value: Any, path: tuple) -> Any:
    parent = _value_at(value, path[:-1])
    key = path[-1]
    if not isinstance(parent, dict) or key not in parent:
        raise CorrectionError("stale_error", "The rejected extra field is no longer present; use the latest diagnostic.")
    return parent.pop(key)


def _array_shape_errors(before: Any, after: Any, path=()) -> list[str]:
    problems = []
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [f"{_model_path(path)} changes array length"]
        for index, (old, new) in enumerate(zip(before, after)):
            if isinstance(old, dict) and isinstance(new, dict):
                for key in _IDENTITY_KEYS:
                    if key in old and key in new and old[key] != new[key]:
                        problems.append(f"{_model_path((*path, index))} changes {key} or array order")
                problems.extend(_array_shape_errors(old, new, (*path, index)))
            elif isinstance(old, (dict, list)) or isinstance(new, (dict, list)):
                problems.extend(_array_shape_errors(old, new, (*path, index)))
    elif isinstance(before, dict) and isinstance(after, dict):
        for key in before.keys() & after.keys():
            problems.extend(_array_shape_errors(before[key], after[key], (*path, key)))
    return problems


def apply_correction(record: CandidateRecord, request: PatchCandidate | ReplaceCandidate) -> CorrectionMerge:
    record.verify(request)
    if isinstance(request, ReplaceCandidate):
        return CorrectionMerge(deepcopy(request.arguments), "replace", request.reason, True)

    diagnostics = _diagnostic_errors(record)
    by_id = {item["error_id"]: item for item in diagnostics}
    seen = set()
    footprints: list[tuple[str, tuple, tuple | None]] = []
    for correction in request.corrections:
        error_id = correction.error_id
        if error_id in seen:
            raise CorrectionError("duplicate_error", f"error_id {error_id!r} was corrected more than once; submit one unambiguous value.", error_id=error_id)
        seen.add(error_id)
        issue = by_id.get(error_id)
        if issue is None:
            raise CorrectionError("unknown_error", f"error_id {error_id!r} is unknown or expired for candidate_digest {record.candidate_digest}; use the latest errors.", error_id=error_id)
        rule = issue["correction"]
        operation = rule.get("operation")
        if operation is None:
            raise CorrectionError("scope_required", f"error_id {error_id!r} does not authorize a local value correction: {rule.get('reason', 'use explicit replace')}", error_id=error_id)
        path = tuple(rule.get("source_path") or rule.get("path") or issue["server_path"])
        destination = tuple(rule["destination_path"]) if operation == "move" else None
        for _, other_source, other_destination in footprints:
            if _paths_overlap(path, other_source) or (destination and other_destination and destination == other_destination):
                raise CorrectionError("conflicting_corrections", f"error_id {error_id!r} overlaps another correction; submit one correction for the shared minimal subtree or use replace.", error_id=error_id)
            if destination and _paths_overlap(destination, other_source):
                raise CorrectionError("conflicting_corrections", f"error_id {error_id!r} writes into another correction's source subtree.", error_id=error_id)
        footprints.append((error_id, path, destination))
        if operation == "wrap":
            footprints.extend((error_id, (*path[:-1], key), None) for key in rule["source_fields"])

    merged = deepcopy(record.arguments)
    for correction in request.corrections:
        issue = by_id[correction.error_id]
        rule = issue["correction"]
        operation = rule["operation"]
        path = tuple(rule.get("source_path") or rule.get("path") or issue["server_path"])
        if operation == "wrap":
            if correction.value != rule["target_token"]:
                raise CorrectionError("invalid_wrap_target", "Use only the declared wrapper token.", error_id=correction.error_id)
            parent_path = path[:-1]
            wrapped = {key: _remove_at(merged, (*parent_path, key)) for key in rule["source_fields"]}
            _set_at(merged, path, wrapped)
        elif operation == "set":
            old = _value_at(record.arguments, path)
            shape = _array_shape_errors(old, correction.value, path)
            if shape:
                raise CorrectionError("structure_requires_replace", "Patch cannot change array length, identity or order: " + "; ".join(shape) + ". Choose explicit replace if that redesign is intended.", error_id=correction.error_id)
            _set_at(merged, path, correction.value)
        elif operation == "remove":
            if correction.value not in (None, ""):
                raise CorrectionError("invalid_correction_value", "operation=remove requires value=null; null here means removing only the rejected extra field.", error_id=correction.error_id)
            _remove_at(merged, path)
        elif operation == "move":
            destination = tuple(rule["destination_path"])
            if correction.value != rule["target_token"]:
                raise CorrectionError("invalid_move_target", f"operation=move accepts only the declared target {rule['target_token']!r}; arbitrary paths are not writable.", error_id=correction.error_id)
            if _value_at(merged, destination) is not None:
                raise CorrectionError("conflicting_corrections", "The move destination is already populated; preserve both through explicit replace rather than overwriting content.", error_id=correction.error_id)
            moved = _remove_at(merged, path)
            _set_at(merged, destination, moved)
    return CorrectionMerge(merged, "patch", None, False)


def correction_tool():
    from app.agents.tool_loop import NATIVE_PRESENTATION, ChatTool

    return ChatTool(
        name=CORRECTION_TOOL_NAME,
        presentation=NATIVE_PRESENTATION,
        terminal=False,
        description=(
            "根据最新校验诊断修正服务端保留且尚未执行的候选。设计不变时用 mode=patch，仅传当前的 error_id/value 对，服务端保留其余内容。"
            "只有有意重新设计时才用 mode=replace，提供原因和完整的新原工具参数。不可混用。修正成功只执行一次原目标工具，不另设写入口。"
        ),
        params_model=CandidateCorrectionArgs,
    )


def exception_errors(exc: Exception) -> list[dict]:
    """Read structured validator facts without changing their message contract."""
    issues = getattr(exc, "issues", None)
    if issues:
        return deepcopy(issues)
    problems = getattr(exc, "problems", None)
    if problems:
        return [{"loc": [], "type": "content_validation", "msg": str(problem)} for problem in problems]
    return [{"loc": [], "type": "content_validation", "msg": str(exc)}]
