@echo off
REM Membuat PenerimaanHoper.exe (folder dist\PenerimaanHoper). Jalankan di Windows dengan Python 3.10+.
setlocal
cd /d "%~dp0"
REM Pengaman: build menghapus dist\PenerimaanHoper. Jangan sampai database uji ikut terhapus.
if exist dist\PenerimaanHoper\data\penerimaan.db (
  echo.
  echo PERINGATAN: dist\PenerimaanHoper\data berisi DATABASE. Build akan MENGHAPUSNYA.
  echo Salin dulu folder "data" dan "backup" dari dist\PenerimaanHoper ke tempat lain,
  echo lalu jalankan build_exe.bat lagi.
  pause
  exit /b 1
)

echo === 1/6 Membuat lingkungan build BARU (bersih) ===
if exist .venv rmdir /s /q .venv
py -3 -m venv .venv
if errorlevel 1 goto gagal
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto gagal
pip install --upgrade pyinstaller pyinstaller-hooks-contrib
if errorlevel 1 goto gagal

echo === 2/6 Menguji Qt dan pustaka di lingkungan build ===
python -c "from PySide6 import QtCore, QtGui, QtWidgets; print('Qt OK, versi', QtCore.__version__)"
if errorlevel 1 (
  echo.
  echo Qt TIDAK bisa dimuat bahkan di lingkungan build.
  echo Penyebab paling umum: Microsoft Visual C++ Redistributable belum terpasang.
  echo Pasang dari https://aka.ms/vs/17/release/vc_redist.x64.exe lalu jalankan ulang.
  goto gagal
)
python -c "import openpyxl, reportlab; print('openpyxl dan reportlab OK')"
if errorlevel 1 goto gagal

echo === 3/6 Membersihkan hasil build lama ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo === 4/6 Membangun aplikasi ===
if not exist assets mkdir assets
set ICON=
if exist assets\app.ico set ICON=--icon assets\app.ico
pyinstaller --noconfirm --clean --windowed --name PenerimaanHoper %ICON% --add-data "assets;assets" --exclude-module tkinter --exclude-module unittest app.py
if errorlevel 1 goto gagal

echo === 5/6 Menyalin berkas pendukung ===
copy /Y config.json dist\PenerimaanHoper\config.json >nul
copy /Y README.md dist\PenerimaanHoper\README.md >nul
copy /Y buat_pintasan.bat dist\PenerimaanHoper\buat_pintasan.bat >nul
xcopy /E /I /Y assets dist\PenerimaanHoper\assets >nul

echo === 6/6 Uji mandiri hasil build (membuka .exe sebentar) ===
del "%TEMP%\penerimaan_hoper_selftest.txt" >nul 2>&1
start /wait "" "dist\PenerimaanHoper\PenerimaanHoper.exe" --selftest
if errorlevel 1 (
  echo.
  echo UJI MANDIRI GAGAL. Hasil .exe TIDAK boleh dipakai.
  if exist "%TEMP%\penerimaan_hoper_selftest.txt" type "%TEMP%\penerimaan_hoper_selftest.txt"
  goto gagal
)
echo Uji mandiri BERHASIL: Qt, tampilan, ekspor Excel/PDF, dan cadangan bekerja di .exe.

echo.
echo Hasil: %CD%\dist\PenerimaanHoper\PenerimaanHoper.exe
powershell -NoProfile -Command "'Ukuran folder hasil: {0:N0} MB' -f ((Get-ChildItem 'dist\PenerimaanHoper' -Recurse | Measure-Object Length -Sum).Sum/1MB)"
echo.
echo Salin HANYA folder dist\PenerimaanHoper ke komputer tujuan (mis. C:\PenerimaanHoper).
echo Folder .venv dan build TIDAK perlu disalin. JANGAN taruh di C:\Program Files.
echo Komputer tujuan WAJIB punya Microsoft Visual C++ Redistributable 2015-2022 (x64):
echo   https://aka.ms/vs/17/release/vc_redist.x64.exe
echo Di komputer tujuan, jalankan buat_pintasan.bat untuk membuat pintasan di Desktop.
pause
exit /b 0

:gagal
echo.
echo BUILD GAGAL. Baca pesan di atas.
pause
exit /b 1
