@echo off
rem civic-patch developer launcher.
rem Starts the backend and frontend in their own windows and opens the site.
rem Keep THIS window open while you work; closing it stops both servers.
title civic-patch dev
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1" %*
