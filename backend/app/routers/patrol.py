"""巡检作业接口：巡检路线模板维护、按模板生成任务、问题转派与处置闭环。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.patrol import HANDLE_TEAMS, PatrolService

router = APIRouter(prefix="/api/patrol", tags=["巡检作业"])

service = PatrolService()

LIST_FIELDS = ["任务编号", "巡检站点", "巡检人员", "巡检期次", "计划日期", "巡检路线", "发现问题", "处置班组", "处置状态", "处置措施", "任务状态"]
STATUSES = ["待巡检", "巡检中", "待处置", "处置中", "待复查", "已关闭"]


@router.get("/options")
def handle_options() -> dict[str, Any]:
    """转派可选项：责任班组名册与处置状态字典，供前端下拉使用。"""
    return {"teams": HANDLE_TEAMS, "statuses": STATUSES}


@router.get("/templates")
def list_templates(site: str | None = Query(default=None, description="按适用站点过滤模板")) -> dict[str, Any]:
    """列出巡检路线模板，可按站点收窄；取不到模板时由生成接口给出说明。"""
    items = service.list_templates(site=site)
    return {"items": items, "total": len(items)}


@router.post("/templates", response_model=ActionResult)
def create_template(payload: EntryPayload) -> ActionResult:
    """保存一条巡检路线模板，巡检点顺序即模板顺序；缺字段时说明原因。"""
    template, missing = service.create_template(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message=f"巡检路线模板「{template['模板名称']}」已保存", entry=template)


@router.post("/generate", response_model=ActionResult)
def generate_entry(payload: EntryPayload) -> ActionResult:
    """按站点挑模板生成本期巡检任务；同站点同期不重复建，取不到模板时只返回说明。"""
    entry, message = service.generate_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按任务编号检索"),
    status: str | None = Query(default=None, description="待巡检、巡检中、待处置、处置中、待复查、已关闭"),
    site: str | None = Query(default=None, description="按巡检站点过滤"),
    period: str | None = Query(default=None, description="按巡检期次过滤，如 2026-10"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按任务编号、状态、站点与期次过滤巡检任务列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, site=site, period=period, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出巡检作业清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "patrol", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条巡检任务明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"巡检任务 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """手工登记一条巡检任务的兜底入口，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="巡检任务已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对巡检任务执行开始巡检、上报问题、转派处置、班组接单、处置完成、复查关闭等动作。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
