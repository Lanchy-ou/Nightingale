# R2B — 分离显示与结构化概念

优先级：P1。执行顺序：R1 → R2A → R3 → R4 → R5 → R2B → R6。

## 实施范围

可空 semantic_context；有限同义词；服务端精确来源上下文验证；新版重复证据和存量回填。

## 验收与证据

从 backend 运行：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_semantic_context.py tests/test_ai_conflict_authority.py tests/test_highlight_provenance.py
```

回归测试覆盖具体边界；最终集成结果、浏览器路径、性能报告及已知限制见
[验收记录](../boundary_acceptance_2026-09-08.md)。执行和数据恢复见
[操作说明](../boundary_repairs.md)。每项修复在最终集成状态统一验收；
提交顺序用于审阅变更，不代表已部署或已在工作数据库回填。

## 兼容与限制

未知不强行合并。旧 entity_key/ID 和来源绑定兼容；不调用模型回填，不改写摘要。
