# GitHub preparation / Подготовка GitHub

## English

Repository: [hyphens-cell/scene](https://github.com/hyphens-cell/scene). The [latest release](https://github.com/hyphens-cell/scene/releases/latest) provides the Windows installer and SHA-256 checksums. Generated `dist/`, `build/`, `artifacts/`, `.venv/` and local records are ignored; binaries belong in release attachments rather than source history. A project license has not yet been selected.

1. Review the English/Russian README, source, tests and `.gitignore`.
2. Choose a project license before presenting it as open source, taking dependency licenses into account. No license was assigned by this preparation.
3. Clone the repository or use its existing local checkout.
4. Inspect `git status` and `git diff --cached`. Stage the intended files, commit using your own configured identity and push:

```powershell
git add .
git diff --cached --stat
git commit -m "Describe the change"
git push -u origin main
```

The Windows workflow runs after each push. Local test results do not imply a successful remote CI run. Attach each verified installer to its versioned release as `Scene-Setup-x64.exe` so the README's latest-download link keeps working; include a checksum file for that exact asset name.

Before a binary release, update the source/package version, build from the reviewed commit, verify the installer in isolation, and test real audio/displays and the required Office/Canva paths. Do not upload a prior 2.2.0 executable as the localized version. Signing requires the owner's code-signing certificate or signing service; never commit its private key.

## Русский

Репозиторий: [hyphens-cell/scene](https://github.com/hyphens-cell/scene). В [последнем релизе](https://github.com/hyphens-cell/scene/releases/latest) доступны установщик Windows и контрольные суммы SHA-256. `dist/`, `build/`, `artifacts/`, `.venv/` и локальные рабочие записи исключены из Git; готовые сборки размещаются во вложениях релиза. Лицензия проекта пока не выбрана.

1. Проверьте README RU/EN, исходники, тесты и `.gitignore`.
2. Выберите лицензию перед публикацией как открытого проекта, учитывая лицензии зависимостей. При подготовке лицензия не назначалась.
3. Клонируйте репозиторий либо используйте существующую локальную копию.
4. Проверьте `git status` и `git diff --cached`, добавьте нужные файлы, создайте коммит от своего настроенного имени и выполните отправку командами выше.

После каждой отправки запускается Windows CI. Локальные результаты не означают, что удалённый CI уже прошёл. Прикрепляйте проверенный установщик к релизу своей версии под именем `Scene-Setup-x64.exe`, чтобы ссылка скачивания последней версии в README оставалась рабочей. Контрольная сумма должна соответствовать этому имени файла.

Перед выпуском обновите версию исходников и пакета, соберите проверенный коммит, выполните изолированный тест установщика и проверки звука, мониторов, Office/Canva. Старый EXE 2.2.0 нельзя выдавать за локализованную версию. Подпись требует сертификата или сервиса владельца; закрытый ключ не должен попадать в Git.
