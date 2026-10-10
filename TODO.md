# TODO — open work

Snapshot: 2026-10-09. All branches below are pushed and in sync with `origin`;
nothing is uncommitted or stashed.

## Open PRs, grouped by what they need

### Waiting on a hardware test — do not merge until confirmed

| PR | Branch | Device | Who tests |
|----|--------|--------|-----------|
| [#156](https://github.com/zigbeefordomoticz/z4d-certified-devices/pull/156) | `snzb-04-contact-sensor` | Sonoff / eWeLink SNZB-04 | Patrick. Open questions on the reporting interval and DS01 still unanswered. |
| [#157](https://github.com/zigbeefordomoticz/z4d-certified-devices/pull/157) | `zg-223z-rain-sensor` | Hobeian ZG-223Z rain sensor | rcrocus, via `Conf/Local-Devices/` |
| [#158](https://github.com/zigbeefordomoticz/z4d-certified-devices/pull/158) | `lumi-switch-t1-power-fix` | Aqara T1 switch module `lumi.switch.n0acn2` + `n0agl1` | Isachris83 on [issue #150](https://github.com/zigbeefordomoticz/z4d-certified-devices/issues/150) |

For #158 the reporter has been given instructions (in French) on issue #150: install the
file via `Conf/Local-Devices/`, **delete and re-pair the device** — widgets are only created
at pairing — and report back with values, or a pairing log with the `Lumi`, `Cluster`,
`WidgetCreation`, `DeviceParameter`, `ReadAttributes` debug categories enabled.
Divisors were deliberately left at 1, so the reported W / kWh / V / A still need checking
against a real load.

### Reviewable now, no hardware needed

| PR | Branch | What |
|----|--------|------|
| [#159](https://github.com/zigbeefordomoticz/z4d-certified-devices/pull/159) | `philips-lwa017-cfgrpt-timeout` | Adds the missing `TimeOut` to both `ConfigureReporting` records in `Philips/LWA017.json`. Pure schema fix. |
| [#160](https://github.com/zigbeefordomoticz/z4d-certified-devices/pull/160) | `cfgrpt-attributes-wrapper-sweep` | Two commits: the `Attributes` wrapper sweep (34 cluster entries, 19 files, plus `Owon/AC221`), and malformed `ReadAttributes` ids (19 files). |
| [#161](https://github.com/zigbeefordomoticz/z4d-certified-devices/pull/161) | `develco-aqszb-110-endpoint` | Two commits: nests `Develco/AQSZB-110.json` under endpoint `26`, and aligns VOC reporting with the ZHA quirk. |

**#160 is the one to think about before merging.** It is behaviour-changing, not cosmetic:
reporting that was never configured starts being configured for 20 devices. The intervals
are the original authors' numbers, not anything invented in the sweep, so if a device turns
chatty afterwards the knob is in that device's own file.

**#161 has no hardware report behind it at all** — the device was never reported by a user,
it surfaced from scanning. Endpoint `26` rests on z2m (`endpoint: {default: 38}`) and the
ZHA quirk (`endpoint_id=38`) agreeing, plus the `HMSZB-110` sibling. Strong, and the current
state is definitely broken, but a `Local-Devices` test would be better if an AQSZB-110 user
ever turns up.

### Merge-order note

#160 deliberately leaves `Hobeian/ZG-223Z.json` `0400` unwrapped, because #157 already
wraps it and two branches touching that line would conflict. Whichever merges second,
re-run the wrapper scan to confirm nothing is left flat.

## Loose ends not acted on

- **`Lixee/ZLinky_TIC.json` `ff66`** is an empty `{}` in `ConfigureReporting`. Inert either
  way, left alone.
- **`Ikea/TRADFRIbulbE27WSglobeopal1055lm.json`** keeps `"Change": {}` on `0006`/`0000`
  (DataType `10`) and `0300`/`0008` (DataType `30`). Both are *discrete*, so `rptChg` is
  omitted and the value is never read — no behaviour change, so no churn added.
- **`Develco/AQSZB-110.json`** keeps `0019` and `000a` on endpoint `26`, though neither
  upstream mentions them and `HMSZB-110` has neither. Inert: `0019` is not bound and its
  `ReadAttributes` entry is empty.
- **`lumi.switch.n0agl1`** keeps `Power` on EP `15` / `Meter` on EP `1f`, unlike the
  reworked `n0acn2` which consolidates on EP `01`. Deliberate — that config is already in
  the field and moving the widgets would orphan existing users' devices.

## Scan scripts worth re-creating

Three throwaway scripts found everything above. They lived in the session scratchpad and are
gone now; each is a short walk over `Certified/**/*.json`:

1. **`ConfigureReporting` shape** — per cluster entry, check for the `Attributes` key; per
   attribute record, check `TimeOut` / `DataType` / `MinInterval` / `MaxInterval` are
   present. A missing wrapper is silently skipped; a missing `TimeOut` is a `KeyError`.
2. **Id widths** — every `Ep` id must be 2 hex digits, every cluster and attribute id
   4, across `Ep`, `ClusterToBind`, `ReadAttributes` and `ConfigureReporting`. An `Ep` key
   that looks like a 4-hex cluster id is the tell for a missing endpoint level.
3. **Live payload validation** — for every wrapped record: string `MinInterval` /
   `MaxInterval` / `TimeOut`, a `DataType` that classifies as analog / discrete / composite
   per `Modules/zigateConsts.py`, and a string `Change` whenever the type is analog. This is
   what caught the two `"Change": {}` records that were about to be brought to life.

## Housekeeping

Note that **any** push to `main` triggers both a version bump and a PyPI publish
(`.github/workflows/ci-cd.yml`, `on: push: branches: [main]`, skipped only for a commit whose
message starts with `Bump to`). So a docs-only or housekeeping push to `main` still cuts a
release of the package.
