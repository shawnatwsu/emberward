@echo off
rem Convert an Orbitfall export (webm) into a LinkedIn-ready MP4 and an
rem optimized GIF. Usage:  scripts\make_gif.bat Downloads\orbitfall.webm
if "%~1"=="" (
  echo usage: make_gif.bat path\to\orbitfall.webm
  exit /b 1
)

rem MP4 (recommended for LinkedIn: keeps the score, small, autoplays)
ffmpeg -y -i "%~1" -c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart -c:a aac -b:a 160k "%~dpn1.mp4"

rem GIF (no audio by nature; palette pass keeps colors clean and size down)
ffmpeg -y -i "%~1" -vf "fps=18,scale=880:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4" "%~dpn1.gif"

echo.
echo wrote %~dpn1.mp4 and %~dpn1.gif
