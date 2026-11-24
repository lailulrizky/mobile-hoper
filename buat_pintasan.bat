@echo off
REM Membuat pintasan "Penerimaan Hoper" di Desktop pengguna yang sedang login.
REM Jalankan dari DALAM folder aplikasi (folder yang berisi PenerimaanHoper.exe).
setlocal
if not exist "%~dp0PenerimaanHoper.exe" (
  echo PenerimaanHoper.exe tidak ditemukan di folder ini.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Penerimaan Hoper.lnk')); $s.TargetPath='%~dp0PenerimaanHoper.exe'; $s.WorkingDirectory='%~dp0'; $s.Description='Penerimaan dan Pemakaian Hoper'; $s.Save()"
if errorlevel 1 (
  echo Gagal membuat pintasan. Buat manual: klik kanan PenerimaanHoper.exe ^> Kirim ke ^> Desktop.
) else (
  echo Pintasan "Penerimaan Hoper" sudah dibuat di Desktop.
)
pause
