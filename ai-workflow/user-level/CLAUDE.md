## Environment

### Windows environment
- This machine runs Windows and the username path contains Cyrillic characters. Do not create .lnk shortcuts through the WScript.Shell COM object, because it mangles the path. Use .bat/.cmd launchers or resolve paths with [Environment]::GetFolderPath and write UTF-8 files.
- The sandbox guard blocks scripts that contain Remove-Item or rm -rf. Do not retry blocked delete commands. Ask the user to run the delete, or move or rename the folder instead.

## Working Style

### Correctness rules
- When pinning GitHub Actions or package versions, use the exact documented tag. Never shorten it to a floating major tag unless you have verified that the tag exists.
- For bugs that recur after a fix, add instrumentation or logging to find the root cause before trying another speculative fix.
