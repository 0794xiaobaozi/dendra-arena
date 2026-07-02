# 实验方案 (protocols)

本目录下的 `.yml` / `.yaml` 文件会在 GUI 中自动扫描。

协议只描述一件事：
- 一个 session 持续多久
- 在 session 的哪些时间点给刺激
- 每次刺激的强度和持续时间是多少

只允许这一种写法：

```yaml
schema_version: 1

protocol:
  id: example_protocol
  name: 示例方案
  total_duration_sec: 540
  shocks:
    - time_sec: 240
      current_mA: 0.9
      duration: 3
    - time_sec: 300
      current_mA: 0.9
      duration: 3
```

## 规则

- 一个文件只写一个方案
- 顶层只允许 `schema_version` 和 `protocol`
- `schema_version` 当前固定为 `1`
- `protocol` 内只允许 `id`、`name`、`total_duration_sec`、`shocks`
- `protocol.shocks` 必须是非空列表
- 每个 `shock` 只允许 `time_sec`、`current_mA`、`duration`
- 不支持 freeze 相关字段
- 不支持顶层散写字段
- 不支持一个文件多个协议

## 字段说明

- `protocol.id`
  方案唯一 ID，建议英文小写加下划线
- `protocol.name`
  GUI 下拉框显示名称
- `protocol.total_duration_sec`
  session 总时长，单位秒；没有限制可填 `0`
- `protocol.shocks[].time_sec`
  从 session 开始算起，到该秒数时触发刺激
- `protocol.shocks[].current_mA`
  刺激强度，单位 mA
- `protocol.shocks[].duration`
  写入设备的持续时间字段

## 示例

- 单次刺激：见 [freeze_shock_example.yml](/F:/Neuro/livefreeze_software/protocols/freeze_shock_example.yml)
- 多次刺激：见 [9min_4_5_6_shock.yml](/F:/Neuro/livefreeze_software/protocols/9min_4_5_6_shock.yml)
