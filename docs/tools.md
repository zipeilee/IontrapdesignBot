# IontrapdesignBot MCP Tool Reference

所有工具通过 MCP 暴露(stdio 或 streamable HTTP)。错误以
`{"error": ..., "traceback": ...}` 返回,agent 应检查 `error` 键。

## 会话管理

### `new_layout(name: str) -> dict`
创建空版图会话。重名报错。

### `list_layouts() -> list[dict]`
列出所有会话:电极数、按 kind 统计、电极名、meta。

### `close_layout(name: str)`
关闭并丢弃会话，同时清除该布局的 BEM 缓存。几何生成、优化、扇出和脚本修改也会主动使对应缓存失效；求解器缓存键包含实际电极坐标与类型。

### `list_electrodes(layout: str) -> dict`
电极清单:name / kind / layer / polygon 数。

## 几何生成

### `generate_trap(layout, trap_type, params=None) -> dict`
参数化生成电极,**替换**版图现有内容。`trap_type`:

| 类型 | 说明 | 关键参数(µm) |
|------|------|--------------|
| `five_wire` | 分段 DC 表面线性阱 | `n_dc_segments, dc_length, dc_width, dc_gap, rf_width, rf_gap, center_width, outer_dc` |
| `x_junction` | X 交叉结 | `arm_dc_segments, dc_width, dc_gap, rf_width, rf_gap, center_width, dc_length` |
| `t_junction` | T 结 | 同上 |
| `two_layer` | 双层阱(实验性几何占位实现,非多层电磁模型) | `layer_gap, electrode_width, electrode_length, n_segments` |
| `racetrack` | 无 junction 的跑道环形表面阱,弯道截面可优化 | `half_length, center_width, rf_width, rf_gap, mid_width, dc_width, dc_gap, dc_length, n_dc_segments, bend_shift, bend_trim, bend_profile` |

电极命名:`RF_L/RF_R`、`CENTER`、`DC<i>_U/DC<i>_L`(five-wire);
junction 为 `RF_CENTER`、`RF_XP/RF_XN/RF_YP/RF_YN`、`DC_<arm>_<i>`。

### `add_fanout(layout, pad_pitch=150, pad_size=100) -> dict`
为每个 DC 电极生成锥形引线 + bonding pad(GDS layer 5),
命名 `TRACE_<名>` / `PAD_<名>`。

## 可视化

### `render_layout(layout, labels=true, xlim=None, ylim=None) -> Image`
渲染 PNG 并作为 MCP image 返回,供 agent 直接看图。

## 场评估

### `evaluate_trap(layout, rf_voltage=100, rf_frequency_mhz=30, ion_mass_amu=171, max_panel_size=10, dc_voltages=None, height_guess=None) -> dict`
BEM 静电求解 + 赝势分析。返回:

```json
{
  "position": [x, y, z],              // µm,总势极小点
  "trap_depth_ev": 0.05,
  "secular_frequencies_mhz": [fx, fy, fz],
  "rf_null_height_um": 52.3
}
```

`max_panel_size`(µm)控制 BEM 精度/速度;同一布局的 solver 有缓存。

### `optimize_trap(layout, trap_type, param_names, p0, objectives, fixed_params=None, min_gap=None, panel_size=8.0, ion_mass_amu=171.0, rf_frequency_mhz=30.0, rf_voltage=100.0, max_evals=300) -> dict`

使用 Nelder-Mead 闭环优化参数化几何。每次评估都会重建几何、执行 BEM
求解并计算目标函数；成功后最优几何会直接替换当前 layout 的电极。

`param_names` 与 `p0` 分别指定待优化参数名和初值，`fixed_params` 指定固定参数。
目标支持：

- `{"type": "null_height", "region": {...}, "target": height_um, "weight": w}`：
  使指定区域的 RF null 高度接近目标。
- `{"type": "null_uniform", "regions": [...], "weight": w}`：
  减小多个区域的 null 高度差及相对 nominal 位置的平面偏移。
- `{"type": "bump", "path": [[x, y], ...], "weight": w}`：
  降低指定路径上的最大赝势；路径高度可用 `z` 指定，或用 `z_from` 引用
  另一个目标的 null 高度。

`min_gap` 是最小电极间距硬约束，`panel_size` 控制每次 BEM 评估的精度与成本。
建议先用较粗面板搜索，再用 `evaluate_trap` 和更细面板验证最优结果。

### `solve_dc_voltages(layout, targets, max_panel_size=10) -> dict`
最小二乘反解 DC 电压。target 形式:
`{"point": [x,y,z], "type": "field_null"}` 或
`{"point": [x,y,z], "type": "potential", "value": V}`。
返回 `{"voltages": {electrode: volts}}`。

## DRC

### `drc_check(layout, min_gap=3.0) -> dict`
所有电极对的最小间距检查;返回违规列表 `{a, b, gap}`。

## I/O

### `save_gds(layout, path)` / `open_gds(path, name=None)`
GDS(unit 1 µm, precision 1 nm)。open 时按文本标签恢复电极命名。

### `save_layout_json(layout, path)` / `open_layout_json(path, name=None)`
IontrapdesignBot JSON 格式,完整保留电极 name/kind/polygons/meta。

## 逃生舱

### `execute_script(layout, code) -> dict`
在会话的 ElectrodeSet(变量 `es`)上执行任意 Python。
命名空间:`np`、`gdstk`、`shapely`、`Electrode`、`ElectrodeSet`。
赋值给 `result` 返回;`stdout` 被捕获。
