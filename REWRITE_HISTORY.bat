@echo off
REM Script para reescribir el historial de commits y remover a claude de los contributors
REM Usa git filter-branch para cambiar el autor de los commits mergeados desde ramas de claude

setlocal enabledelayedexpansion

echo.
echo === Reescribiendo historial para remover a claude ===
echo.
echo Este proceso:
echo  1. Cambia el autor de los commits de claude a tu usuario
echo  2. Elimina las ramas claude/*
echo  3. Fuerza el push a main
echo.
pause

REM Cambiar autor de todos los commits hechos por "claude" en el historial
REM (mantiene el committer original, solo cambia author)
git filter-branch -f --env-filter ^
    "if [[ $GIT_COMMITTER_NAME == 'claude' ]] || [[ $GIT_AUTHOR_NAME == 'claude' ]]; then" ^
    "  export GIT_AUTHOR_NAME='Nicand16'; " ^
    "  export GIT_AUTHOR_EMAIL='145942549+Nicand16@users.noreply.github.com'; " ^
    "fi" ^
    HEAD

if !ERRORLEVEL! neq 0 (
    echo ERROR: git filter-branch fallo
    pause
    exit /b 1
)

echo.
echo Historial reescrito. Eliminando ramas de claude...
echo.

REM Eliminar referencias locales
git branch -D claude/dual-provider-llm 2>nul
git branch -D claude/hardcore-pascal-4726e0 2>nul

REM Forzar push a main
echo Haciendo force-push a main...
git push -f origin main

REM Limpiar referencias remotas de las ramas eliminadas
git push origin :claude/dual-provider-llm 2>nul
git push origin :claude/hardcore-pascal-4726e0 2>nul

echo.
echo === Completado ===
echo claude ha sido removido del historial.
echo.
pause
