# Validator Report
- severity: **warning**
- excel sheets: 2
- config sheets: 2, paragraphs: 3
- planned_skips: {'sheets': [], 'paragraphs': ['Conclusion', 'Excretion', 'fill_para']}
- simulate_render: enabled=False, ok=None, error=None

## Template Placeholders (clean)
- **Variables**
  - `fig_sum.average_time_daily_excretion`
  - `fig_sum.main_time_excretion`
  - `sum_total.cum_recov_rate_urine`
  - `sum_total.total_recov_rate_urine_feces`
- **Paragraph IDs**
  - `Conclusion`
  - `Excretion`

## Findings
- **WARNING** | KEY: Excretion 的字段不在 fig_sum.keys 声明中：fig_sum.main_time_excretion
- **WARNING** | KEY: Conclusion 的字段不在 fig_sum.keys 声明中：fig_sum.main_time_excretion
- **WARNING** | KEY: fill_para 的字段不在 fig_sum.keys 声明中：fig_sum.main_time_excretion
- **WARNING** | TEMPLATE: 模板变量字段未在 keys 声明：`fig_sum.main_time_excretion`