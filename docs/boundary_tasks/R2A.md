# R2A — 阻止明显实体和风险误判

优先级：P0。执行顺序：R1 → R2A → R3 → R4 → R5 → R2B → R6。

## 实施范围

Unicode 归一化；排除通用标签；备用风险在分句中检查否定、家属、历史、假设。

## 验收与证据

从 backend 运行：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_boundary_repairs.py tests/test_ai_pipeline_fallback.py
```

回归测试覆盖具体边界；最终集成结果、浏览器路径、性能报告及已知限制见
[验收记录](../boundary_acceptance_2026-09-08.md)。执行和数据恢复见
[操作说明](../boundary_repairs.md)。每项修复在最终集成状态统一验收；
提交顺序用于审阅变更，不代表已部署或已在工作数据库回填。

## 兼容与限制

有限确定性规则，不保证通用医学理解。紧急情况升级规则保持独立。
