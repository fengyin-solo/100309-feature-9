"""巡检作业业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "patrol"
TEMPLATE_MODULE = "patroltpl"
REQUIRED_FIELDS = ["任务编号", "巡检站点", "巡检人员"]
STATUS_ORDER = ["待巡检", "巡检中", "已巡检", "待复查"]
ACTION_RULES = {"开始巡检": "巡检中", "提交巡检": "已巡检", "发起复查": "待复查"}
NEGATIVE_ACTIONS: list[str] = []
HANDLING_STATUSES = ["未转派", "待处置", "已处置"]
TEMPLATE_REQUIRED_FIELDS = ["模板名称", "适用站点"]
POINT_SEPARATORS = ["→", "、", ",", "，", ";", "；", "\n"]


def _next_code(rows: list[dict[str, Any]], field: str, prefix: str) -> str:
    seq = 0
    for row in rows:
        code = str(row.get(field) or "")
        if not code.startswith(prefix):
            continue
        try:
            seq = max(seq, int(code[len(prefix):]))
        except ValueError:
            continue
    return f"{prefix}{seq + 1:04d}"


def _parse_points(value: Any) -> list[str]:
    """巡检点既接受数组，也接受用顿号、逗号或箭头串起来的一行文本。"""
    if isinstance(value, list):
        return [str(point).strip() for point in value if str(point).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    for sep in POINT_SEPARATORS:
        text = text.replace(sep, "|")
    return [point.strip() for point in text.split("|") if point.strip()]


class PatrolService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        site: str | None = None,
        period: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if site:
            rows = [row for row in rows if site in str(row.get("巡检站点", ""))]
        if period:
            rows = [row for row in rows if str(row.get("巡检期次", "")) == period]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["巡检期次"] = str(values.get("巡检期次") or "").strip()
        entry["巡检点列表"] = _parse_points(values.get("巡检点列表"))
        entry["模板编号"] = str(values.get("模板编号") or "").strip()
        entry["处置班组"] = ""
        entry["处置状态"] = HANDLING_STATUSES[0]
        entry["处置结果"] = ""
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def list_templates(
        self,
        *,
        site: str | None = None,
        page: int = 1,
        size: int = 200,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(TEMPLATE_MODULE)
        if site:
            rows = [row for row in rows if str(row.get("适用站点", "")) == site]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def create_template(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        missing = [field for field in TEMPLATE_REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        points = _parse_points(values.get("巡检点列表"))
        if not points:
            return None, "巡检路线模板至少要有一个巡检点，请按顺序填写"
        rows = store.rows(TEMPLATE_MODULE)
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "模板编号": _next_code(rows, "模板编号", "TPL-"),
            "模板名称": str(values.get("模板名称") or "").strip(),
            "适用站点": str(values.get("适用站点") or "").strip(),
            "责任班组": str(values.get("责任班组") or "").strip(),
            "巡检点列表": points,
            "备注": str(values.get("备注") or "").strip(),
            "status": "启用",
            "pending": False,
            "abnormal": False,
        }
        rows.append(entry)
        return entry, None

    def generate_task(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, bool, str]:
        """按站点+期次从路线模板生成本期巡检任务；同站同期只留一条，取不到模板不生成空任务。"""
        site = str(values.get("巡检站点") or "").strip()
        period = str(values.get("巡检期次") or "").strip()
        if not site or not period:
            return None, False, "生成本期巡检任务需要同时填写巡检站点和巡检期次"
        rows = store.rows(MODULE)
        for row in rows:
            if str(row.get("巡检站点", "")) == site and str(row.get("巡检期次", "")) == period:
                return row, True, (
                    f"{site} {period} 期的巡检任务已存在（{row.get('任务编号')}），"
                    "同一站点同一期只保留一条，本次未重复生成"
                )
        template, message = self._pick_template(site, str(values.get("模板编号") or "").strip())
        if template is None:
            return None, False, message
        points = [str(point) for point in template.get("巡检点列表") or [] if str(point).strip()]
        if not points:
            return None, False, f"模板 {template.get('模板编号')} 里没有巡检点，请先完善模板再生成任务"
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "任务编号": _next_code(rows, "任务编号", "PATR-"),
            "巡检站点": site,
            "巡检人员": str(values.get("巡检人员") or "").strip() or "待指派",
            "巡检期次": period,
            "计划日期": str(values.get("计划日期") or "").strip() or date.today().isoformat(),
            "巡检路线": "→".join(points),
            "巡检点列表": list(points),
            "模板编号": template.get("模板编号", ""),
            "发现问题": "",
            "处置班组": "",
            "处置状态": HANDLING_STATUSES[0],
            "处置措施": "",
            "处置结果": "",
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
        }
        rows.append(entry)
        return entry, True, (
            f"已按模板 {template.get('模板编号')}（{template.get('模板名称')}）生成 {site} {period} 期巡检任务，"
            f"共 {len(points)} 个巡检点，顺序与模板一致"
        )

    def _pick_template(self, site: str, template_code: str) -> tuple[dict[str, Any] | None, str]:
        templates = store.rows(TEMPLATE_MODULE)
        if template_code:
            for template in templates:
                if str(template.get("模板编号", "")) == template_code:
                    if str(template.get("适用站点", "")) != site:
                        return None, (
                            f"模板 {template_code} 的适用站点是「{template.get('适用站点')}」，"
                            f"不能用于「{site}」生成任务"
                        )
                    return template, ""
            return None, f"巡检路线模板 {template_code} 不存在，请先在模板库登记"
        candidates = [
            template for template in templates
            if str(template.get("适用站点", "")) == site and template.get("status") == "启用"
        ]
        if not candidates:
            return None, (
                f"站点「{site}」还没有可用的巡检路线模板，"
                "请先在模板库为该站点登记路线模板，再生成本期任务"
            )
        return candidates[0], ""

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"巡检任务 {entry_id} 不存在或已归档"
        if action == "转派处置":
            return self._dispatch(entry, values)
        if action == "处置完成":
            return self._complete_handling(entry, values)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于巡检作业可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if action == "提交巡检":
            problem = str(values.get("发现问题") or "").strip()
            if problem:
                entry["发现问题"] = problem
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"巡检任务已{action}"

    def _dispatch(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """把巡检发现的问题转派给责任班组，任务上留下处置班组与处置状态。"""
        if not str(entry.get("发现问题") or "").strip():
            return None, "该任务还没有记录发现问题，无需转派处置"
        handling = str(entry.get("处置状态") or HANDLING_STATUSES[0])
        if handling == "待处置":
            return None, f"问题已转派给{entry.get('处置班组')}，处置尚未完成，请勿重复转派"
        if handling == "已处置":
            return None, "问题已处置完成，无需再次转派"
        team = str(values.get("处置班组") or "").strip() or self._default_team(entry)
        if not team:
            return None, "请指定承接处置的责任班组"
        entry["处置班组"] = team
        entry["处置状态"] = "待处置"
        return entry, f"发现问题已转派给{team}，等待处置"

    def _complete_handling(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """处置班组办结后，把处置结果写回原巡检任务。"""
        handling = str(entry.get("处置状态") or HANDLING_STATUSES[0])
        if handling == "未转派":
            return None, "任务尚未转派责任班组，请先执行转派处置"
        if handling == "已处置":
            return None, "处置结果已回填，请勿重复操作"
        result = str(values.get("处置结果") or "").strip()
        if not result:
            return None, "请填写处置结果，再确认处置完成"
        entry["处置结果"] = result
        entry["处置措施"] = result
        entry["处置状态"] = "已处置"
        return entry, f"处置完成，结果已写回巡检任务（处置班组：{entry.get('处置班组')}）"

    def _default_team(self, entry: dict[str, Any]) -> str:
        template_code = str(entry.get("模板编号") or "").strip()
        if not template_code:
            return ""
        for template in store.rows(TEMPLATE_MODULE):
            if str(template.get("模板编号", "")) == template_code:
                return str(template.get("责任班组") or "").strip()
        return ""
