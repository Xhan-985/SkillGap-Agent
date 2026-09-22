"""贡献端点（API.md §2.14 DELETE contributions——T4 将增补 §2.2 POST
jd/contribute + tasks 异步查询，本文件先行落位删除闭环）。

§2.14 纪律：哈希比对删除（DATA_GOVERNANCE §3）；不存在与已删除一律
404 不区分（防探测）；无路径参数格式校验——任何无效格式自然哈希
不匹配 → 404，不暴露 code 有效性信息。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from skillgap.api.deps import get_conn
from skillgap.api.errors import ApiError
from skillgap.ingest.contribute import delete_contribution

router = APIRouter(prefix="/api/contributions", tags=["contribute"])


@router.delete("/{deletion_code}", status_code=204)
def delete(deletion_code: str, conn=Depends(get_conn)):
    """§2.14 凭 code 删除贡献（级联 job_skill/deletion_code）；库中
    只存哈希，明文 code 不落库。"""
    if not delete_contribution(conn, deletion_code):
        raise ApiError(404, "NOT_FOUND", "deletion_code 无效或贡献已删除")
    return Response(status_code=204)
