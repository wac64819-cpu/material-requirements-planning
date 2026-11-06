# GitHub 同类项目参考与本项目取舍

查阅日期：2026-09-26。依据官方仓库说明和官方功能文档；本轮没有安装这些系统，也没有复制其源码。

| 项目 | 与本题相关的内容 | 本项目如何参考 |
|---|---|---|
| [frePPLe](https://github.com/frePPLe/frepple) | 需求排序、库存抵扣、日期倒推、采购批量 | 重点参考计算步骤；采用用户已确认的任务优先级优先 |
| [ERPNext](https://github.com/frappe/erpnext) | 生产计划、子装配件、采购需求 | 参考生产与采购结果的组织及库存后缺口的展示 |
| [OCA / mrp_multi_level](https://github.com/OCA/manufacture/tree/18.0/mrp_multi_level) | 多层 MRP、计划订单、采购参数 | 参考先计算计划、再处理订单的业务阶段；本项目只输出建议 |

## 最值得借鉴的三点

1. **排序先于库存分配。** frePPLe 官方[功能文档](https://github.com/frePPLe/frepple/blob/master/doc/features.rst)明确先按优先级、再按交期处理需求，并抵扣已有库存。这与 BR03 一致；本项目再用任务编号确定同级同日顺序。其产能约束、替代方案和正向重排不在本次范围。
2. **生产与采购缺口分开显示。** ERPNext 官方[生产计划文档](https://docs.frappe.io/erpnext/production-plan)包含子装配项和采购需求，并支持考虑预计可用数量。我们的口径只使用“账面库存－已占用库存”，不纳入未到货订单，不能直接套用它的预计库存数值。
3. **计划与执行分开。** OCA [模块说明](https://github.com/OCA/manufacture/tree/18.0/mrp_multi_level)包含 MRP 计算和后续补货操作，也记录了采购倍数支持。本项目计算不扣真实库存、不创建采购订单，便于复算和测试。

## 本轮自行实现

过程式函数完成输入和可达 BOM 校验、拓扑顺序展开、优先级库存分配、同日缺口合并、按日期使用余量和风险标注。来源记录保留任务、父需求、BOM 路径、库存分配和余量关联。

具体字段、来源分配顺序、余量规则和验收数据来自本项目已有 E1/E2 草案；不声称三个开源系统都采用完全相同的实现。原型没有自定义类，未引入 ERP 框架。

## 当前交付与下一步

计算程序见 `material-planning/planner.py`，演示见 `material-planning/results/demo-plans.html`。

下一阶段接入基础数据维护、整批保存和历史查询，再提供操作界面与 CSV。完整 E3/E4/E5 继续补充；计算验证不能替代全部实验要求。
