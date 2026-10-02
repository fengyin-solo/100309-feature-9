"""巡检作业业务规则：巡检路线模板、按模板生成任务、问题转派与处置闭环都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "patrol"
TEMPLATE_MODULE = "patrol_template"

REQUIRED_FIELDS = ["任务编号", "巡检站点", "巡检人员"]
TEMPLATE_REQUIRED_FIELDS = ["模板名称", "适用站点", "巡检点"]

# 巡检任务主状态：从待巡检一路走到关闭；有问题的任务要等处置闭环后才能关闭。
STATUS_ORDER = ["待巡检", "巡检中", "待处置", "处置中", "待复查", "已关闭"]
# 处置状态是问题转派后的处置进度，独立挂在任务上，处置结果会回写到原任务。
HANDLE_STATUSES = ["无需处置", "待处置", "处置中", "已处置"]
DISPATCHABLE_STATUSES = {"巡检中", "待处置", "处置中"}

ACTION_RULES = {
    "开始巡检": "巡检中",
    "提交巡检": "待复查",
    "发起复查": "待复查",
    "复查关闭": "已关闭",
}

# 责任班组清单：转派时只能挑在册班组，避免问题转丢。
HANDLE_TEAMS = ["动力班组", "无线班组", "传输班组", "铁塔班组", "消防班组", "综合班组"]

ROUTE_SEPARATORS = ["，", ",", "、", ";", "；", "\n"]


def _today() -> str:
    return date.today().isoformat()


def _current_period() -> str:
    return date.today().strftime("%Y-%m")


def _split_points(raw: Any) -> list[str]:
    """把文本框里的巡检点拆成有序列表，顺序照搬，自动去空、去重。"""
    if isinstance(raw, list):
        items = [str(item).strip() for item in raw]
    else:
        text = str(raw or "")
        for separator in ROUTE_SEPARATORS[1:]:
            text = text.replace(separator, ROUTE_SEPARATORS[0])
        items = [part.strip() for part in text.split(ROUTE_SEPARATORS[0])]
    points: list[str] = []
    for item in items:
        if item and item not in points:
            points.append(item)
    return points


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


def _task_no(rows: list[dict[str, Any]]) -> str:
    return f"PATR-{len(rows) + 1:04d}"


class PatrolService:
    # ------------------------------------------------------------------ 任务
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
        """手工登记的兜底入口，正常建任务走 generate_entry（按模板生成）。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": _next_id(rows)}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry.update({
            "任务编号": str(values.get("任务编号") or _task_no(rows)),
            "巡检期次": str(values.get("巡检期次") or _current_period()),
            "计划日期": str(values.get("计划日期") or _today()),
            "巡检点": _split_points(values.get("巡检点") or values.get("巡检路线")),
            "巡检路线": str(values.get("巡检路线") or ""),
            "发现问题": "",
            "处置班组": "",
            "处置状态": "无需处置",
            "处置措施": "",
            "处置记录": [],
            "模板编号": values.get("模板编号"),
            "status": "待巡检",
            "任务状态": "待巡检",
            "pending": True,
            "abnormal": False,
        })
        if not entry["巡检路线"]:
            entry["巡检路线"] = " → ".join(entry["巡检点"])
        rows.append(entry)
        return entry, []

    def generate_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """按站点+期次取模板生成本期任务：同站点同期只留一条，取不到模板时只给说明。"""
        site = str(values.get("巡检站点") or "").strip()
        period = str(values.get("巡检期次") or _current_period()).strip()
        inspector = str(values.get("巡检人员") or "").strip()
        if not site:
            return None, "请先选择巡检站点，再按模板生成任务"
        if not inspector:
            return None, "请填写巡检人员，否则任务无人承接"

        rows = store.rows(MODULE)
        for existing in rows:
            if str(existing.get("巡检站点", "")).strip() == site and str(existing.get("巡检期次", "")) == period:
                return existing, f"站点「{site}」{period} 期巡检任务已存在（{existing['任务编号']}），不重复生成"

        template = self._find_template(site)
        if template is None:
            return None, f"站点「{site}」还没有可用的巡检路线模板，请先在「巡检路线模板」里维护，未生成空任务"

        points = list(template.get("巡检点") or [])
        entry = {
            "id": _next_id(rows),
            "任务编号": _task_no(rows),
            "巡检站点": site,
            "巡检人员": inspector,
            "巡检期次": period,
            "计划日期": str(values.get("计划日期") or _today()),
            "模板编号": template["id"],
            "巡检点": points,
            # 巡检点顺序照搬模板，展示成一条路线。
            "巡检路线": " → ".join(points),
            "发现问题": "",
            "处置班组": "",
            "处置状态": "无需处置",
            "处置措施": "",
            "处置记录": [],
            "status": "待巡检",
            "任务状态": "待巡检",
            "pending": True,
            "abnormal": False,
        }
        rows.append(entry)
        return entry, f"已按模板「{template['模板名称']}」生成 {period} 期巡检任务，共 {len(points)} 个巡检点"

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"巡检任务 {entry_id} 不存在或已归档"
        values = values or {}

        if action == "上报问题":
            return self._report_problem(entry, values)
        if action == "转派处置":
            return self._dispatch(entry, values)
        if action == "班组接单":
            return self._accept(entry)
        if action == "处置完成":
            return self._finish_handling(entry, values)

        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于巡检作业可执行范围"
        target = ACTION_RULES[action]
        # 提交巡检时带着发现问题一起入库；有问题则转入待处置，而不是直接复查。
        if action == "提交巡检":
            problem = str(values.get("发现问题") or "").strip()
            if problem:
                return self._report_problem(entry, {"发现问题": problem})
            entry["发现问题"] = ""
            entry["处置状态"] = "无需处置"
        if action == "复查关闭" and entry.get("发现问题") and entry.get("处置状态") != "已处置":
            return None, "该任务仍有问题未处置闭环，不能关闭"
        entry["status"] = target
        entry["任务状态"] = target
        entry["pending"] = target != "已关闭"
        entry["abnormal"] = bool(entry.get("发现问题")) and entry.get("处置状态") != "已处置"
        return entry, f"巡检任务已{action}"

    # ------------------------------------------------------------- 问题与处置
    def _report_problem(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        problem = str(values.get("发现问题") or "").strip()
        if not problem:
            return None, "请填写巡检发现的问题，再上报或转派"
        if entry["status"] in ("待巡检", "已关闭"):
            return None, f"任务处于「{entry['任务状态']}」，请先开始巡检后再上报问题"
        entry["发现问题"] = problem
        entry["status"] = "待处置"
        entry["任务状态"] = "待处置"
        entry["处置状态"] = "待处置"
        entry["处置班组"] = ""
        entry["处置措施"] = ""
        entry["pending"] = True
        entry["abnormal"] = True
        entry.setdefault("处置记录", []).append(
            {"班组": "", "状态": "待处置", "问题": problem, "措施": "", "时间": _today()}
        )
        return entry, "问题已登记，等待转派责任班组"

    def _dispatch(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        problem = str(values.get("发现问题") or entry.get("发现问题") or "").strip()
        team = str(values.get("处置班组") or "").strip()
        if not problem:
            return None, "还没有巡检发现的问题，不能转派"
        if not team:
            return None, "请选择处置责任班组后再转派"
        if team not in HANDLE_TEAMS:
            return None, f"处置班组「{team}」不在责任班组名册里"
        if entry["status"] not in DISPATCHABLE_STATUSES:
            return None, f"任务处于「{entry['任务状态']}」，当前不能转派"
        entry["发现问题"] = problem
        entry["处置班组"] = team
        # 转派后任务带上处置班组与处置状态，进入班组处置环节。
        entry["处置状态"] = "待处置"
        entry["status"] = "待处置"
        entry["任务状态"] = "待处置"
        entry["pending"] = True
        entry["abnormal"] = True
        entry.setdefault("处置记录", []).append(
            {"班组": team, "状态": "待处置", "问题": problem, "措施": "", "时间": _today()}
        )
        return entry, f"问题已一键转派给{team}，等待班组接单处置"

    def _accept(self, entry: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if not entry.get("处置班组"):
            return None, "任务还未转派责任班组，无法接单"
        if entry["处置状态"] == "已处置":
            return None, "该问题已处置完成，无需重复接单"
        entry["处置状态"] = "处置中"
        entry["status"] = "处置中"
        entry["任务状态"] = "处置中"
        entry.setdefault("处置记录", []).append(
            {"班组": entry["处置班组"], "状态": "处置中", "问题": entry.get("发现问题", ""), "措施": "", "时间": _today()}
        )
        return entry, f"{entry['处置班组']}已接单，问题处置中"

    def _finish_handling(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        measure = str(values.get("处置措施") or "").strip()
        if not entry.get("处置班组"):
            return None, "任务还未转派责任班组，不能回填处置结果"
        if entry["处置状态"] == "已处置":
            return None, "该问题已处置完成，不要重复回填"
        if not measure:
            return None, "请填写处置措施与结果，再提交处置完成"
        # 处置结果写回原巡检任务，任务交回巡检侧复查。
        entry["处置措施"] = measure
        entry["处置状态"] = "已处置"
        entry["status"] = "待复查"
        entry["任务状态"] = "待复查"
        entry["pending"] = True
        entry["abnormal"] = False
        entry.setdefault("处置记录", []).append(
            {"班组": entry["处置班组"], "状态": "已处置", "问题": entry.get("发现问题", ""), "措施": measure, "时间": _today()}
        )
        return entry, f"{entry['处置班组']}处置结果已写回巡检任务，等待复查关闭"

    # ------------------------------------------------------------------ 模板
    def list_templates(self, site: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(TEMPLATE_MODULE)
        if site:
            rows = [row for row in rows if site in str(row.get("适用站点", ""))]
        return rows

    def get_template(self, template_id: int) -> dict[str, Any] | None:
        return store.find(TEMPLATE_MODULE, template_id)

    def create_template(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        name = str(values.get("模板名称") or "").strip()
        site = str(values.get("适用站点") or "").strip()
        points = _split_points(values.get("巡检点"))
        missing = [
            label
            for label, value in (("模板名称", name), ("适用站点", site), ("巡检点", "、".join(points)))
            if not value
        ]
        if missing:
            return None, missing
        rows = store.rows(TEMPLATE_MODULE)
        template = {
            "id": _next_id(rows),
            "模板名称": name,
            "适用站点": site,
            "巡检点": points,
            "巡检路线": " → ".join(points),
            "备注": str(values.get("备注") or "").strip(),
        }
        rows.append(template)
        return template, []

    def _find_template(self, site: str) -> dict[str, Any] | None:
        """同站点多模板时取最近维护的一条；站点没有专属模板时不允许套用别的站点。"""
        matches = [
            row for row in store.rows(TEMPLATE_MODULE)
            if str(row.get("适用站点", "")).strip() == site
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda row: int(row.get("id", 0)), reverse=True)[0]
