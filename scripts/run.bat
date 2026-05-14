@echo off
REM ============================================================================
REM scripts\run.bat - one-paste batch renderer.
REM
REM After scripts\install.bat has been run once and the caches are warm,
REM this is the only command needed to crank out videos. Open ANY cmd
REM window, cd into the repo, and run:
REM
REM     scripts\run.bat              -- prompts "How many videos?"
REM     scripts\run.bat 10           -- skip the prompt, render 10 videos
REM     scripts\run.bat 10 nosleep   -- 10 videos, single specific subreddit
REM
REM What it does:
REM   1. Verifies .venv\Scripts\yt-shorts-factory.exe is present.
REM   2. Optionally prompts for a video count.
REM   3. Calls `yt-shorts-factory batch` against a curated rotation of
REM      story-heavy subreddits (drama / horror / infidelity / family).
REM   4. Opens explorer on the `out\` folder when done.
REM
REM Persistence:
REM   - Cache (gameplay / ASMR / Kokoro / SFX / dedup db) is reused
REM     across runs. You only ever pay download cost once.
REM   - Dedup db (cache\processed.sqlite) prevents re-rendering the same
REM     Reddit post even across separate runs.
REM ============================================================================

setlocal
set HERE=%~dp0
cd /d "%HERE%\.."

if not exist .venv\Scripts\yt-shorts-factory.exe (
    echo.
    echo [run.bat] .venv\Scripts\yt-shorts-factory.exe not found.
    echo Run scripts\install.bat first to set up the environment.
    echo.
    pause
    exit /b 1
)

REM Args:  %1 = count (optional),  %2 = single subreddit (optional)
set COUNT=%~1
set SINGLE_SUB=%~2

if "%COUNT%"=="" (
    set /p COUNT="How many videos to render? [default: 5] "
)
if "%COUNT%"=="" set COUNT=5

REM Validate count is numeric.
echo %COUNT%|findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo [run.bat] Invalid count: "%COUNT%". Must be a positive integer.
    pause
    exit /b 1
)

REM Curated rotation: heavy on infidelity / family / horror -- the
REM categories that retain best after the title_only hook change.
set SUBS=AITAH,survivinginfidelity,nosleep,BestofRedditorUpdates,cheating_stories,JustNoMIL,TwoSentenceHorror,offmychest,raisedbynarcissists,EntitledParents

if not "%SINGLE_SUB%"=="" (
    set SUBS=%SINGLE_SUB%
)

echo.
echo [run.bat] Rendering %COUNT% video(s) from: %SUBS%
echo [run.bat] Output: %CD%\out
echo.

call .venv\Scripts\yt-shorts-factory.exe batch --count %COUNT% --subreddits %SUBS% -v
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
    echo.
    echo [run.bat] Batch run exited with code %RC%.
    pause
    exit /b %RC%
)

echo.
echo [run.bat] Done. Opening output folder...
start "" explorer "%CD%\out"

endlocal
