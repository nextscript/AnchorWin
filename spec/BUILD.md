# Build instructions – AnchorWin v1.0

## Prerequisites (one-time)

Python 3.12+ recommended; Python 3.14 present.

```sh
python -m pip install --no-cache-dir PySide6 psutil pywin32
python -m pip install --no-cache-dir pyinstaller
```

## 1. Icon (optional, already done)

`icon.ico` at the repository root is bundled by PyInstaller
(`build/AnchorWin.spec`) and used by the app at runtime.


## 2. Obfuscation with PyArmor (optional)

```sh
pyarmor gen -i . -r .
```

## 3. PyInstaller build

```sh
pyinstaller --noconfirm --clean build/AnchorWin.spec
```

The binary is `dist/AnchorWin/AnchorWin.exe`.

## 4. Test

```sh
dist\AnchorWin\AnchorWin.exe --selftest
```

## 5. CI release (GitHub Actions)

`.github/workflows/release.yml` runs on every push to `main`. If a pushed
commit message contains a version like `v1.0`, the workflow builds the EXE
on Windows and publishes a GitHub Release (tag `v1.0` is pushed
automatically). Commits without a version build nothing.

## Troubleshooting

- **PermissionError while building:** Defender scanning the output folder. Add
  `dist\` as an exclusion under Windows Security → Virus & threat protection →
  Manage exclusions.
- **Missing icon:** check `icon.ico` exists at the repository root.

## Versioning

v1.0 – release of the suite (calculation/conversion/analysis/upgrade).
