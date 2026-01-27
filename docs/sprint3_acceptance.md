# Sprint 3 Acceptance (PC)

## Quick Start

1) Synthetic multi-channel DOA (no mic array required):

```
python apps/audio/doa_offline.py --config configs/doa.yaml --run latest
```

2) Real multichannel wav:

```
python apps/audio/doa_offline.py --config configs/doa.yaml --run latest --input path\to\audio.wav
```

## Expected Outputs

- runs/<run_id>/observations/audio_doa.jsonl
- runs/<run_id>/metrics.jsonl (doa_eval when synth enabled)

## Notes

- Synthetic test writes `runs/<run_id>/audio/audio_synth.wav` for inspection.
- For a real mic array, use a multichannel WAV with known geometry and update `configs/doa.yaml`.
- Use `window` and `pre_emphasis` to improve GCC-PHAT stability on noisy data.
- Use `pair_mode` to switch between reference-channel and adjacent-channel pairs.
