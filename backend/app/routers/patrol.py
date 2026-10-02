"""巡检作业接口：维护巡检任务与路线模板，覆盖按模板生成、开始巡检、转派处置等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.patrol import PatrolService

router = APIRouter(prefix="/api/patrol", tags=["巡检作业"])

service = PatrolService()

LIST_FIELDS = ["任务编号", "巡检站点", "巡检人员", "巡检期次", "计划日期", "巡检路线", "发现问题", "处置班组", "处置状态", "处置措施", "任务状态"]
STATUSES = ["待巡检", "巡检中", "已巡检", "待复查"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按任务编号检索"),
    status: str | None = Query(default=None, description="待巡检、巡检中、已巡检、待复查"),
    site: str | None = Query(default=None, description="按巡检站点过滤"),
    period: str | None = Query(default=None, description="按巡检期次过滤，如 2026-10"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按任务编号、站点、期次与状态过滤巡检作业列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, site=site, period=period, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/templates", response_model=PageResult[dict])
def list_templates(
    site: str | None = Query(default=None, description="按适用站点过滤模板"),
    page: int = 1,
    size: int = 200,
) -> PageResult[dict]:
    """列出巡检路线模板；生成任务前可以先按站点查可用模板。"""
    items, total = service.list_templates(site=site, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/templates", response_model=ActionResult)
def create_template(payload: EntryPayload) -> ActionResult:
    """登记一条巡检路线模板：巡检点按填写顺序保存，生成任务时照搬。"""
    entry, error = service.create_template(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=error or "模板登记失败")
    return ActionResult(ok=True, message=f"巡检路线模板 {entry.get('模板编号')} 已登记", entry=entry)


@router.post("/generate", response_model=ActionResult)
def generate_task(payload: EntryPayload) -> ActionResult:
    """按站点+期次从模板生成本期巡检任务；同站同期只留一条，取不到模板时说明原因。"""
    entry, ok, message = service.generate_task(payload.values)
    return ActionResult(ok=ok, message=message, entry=entry)


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
    """登记一条巡检任务，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="巡检任务已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条巡检任务执行开始巡检、提交巡检、转派处置、处置完成、发起复查；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
