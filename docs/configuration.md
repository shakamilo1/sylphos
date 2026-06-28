# Sylphos configuration

Sylphos keeps shared defaults and personal machine settings separate so the
repository can be published safely.

## Files

- `config/voice.py` contains safe default voice-chain values and loads the
  project-root `local_config.py` when it exists.
- `sylphos/config/defaults.py` contains safe runtime defaults.
- `local_config.example.py` is the committed template for all user-editable
  settings.
- `local_config.py` is your private machine-specific configuration. It is
  ignored by Git and should not be committed.

## First-time setup

Option 1: copy the example file and edit it:

```bash
cp local_config.example.py local_config.py
```

Option 2: run the guided setup:

```bash
python setup_config.py
```

The setup command creates `local_config.py` when it does not exist. If it
already exists, the default action is to keep it and write a generated candidate
such as `local_config.generated.py` instead. This prevents `git pull` or setup
reruns from overwriting your personal device names, model paths, tokens, or
recording preferences.

## Rules for contributors

- Keep personal paths, usernames, device names, tokens, passwords, and private
  model directories out of tracked files.
- Put local overrides only in project-root `local_config.py`.
- Runtime code should continue to import `config` or project configuration
  helpers; business modules should not import `local_config.py` directly.
- Use relative example paths such as `models/wakeword/example.onnx` in docs and
  examples.
