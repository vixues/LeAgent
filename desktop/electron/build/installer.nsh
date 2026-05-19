; LeAgent NSIS custom installer hooks
; Included by electron-builder via nsis.include in electron-builder.yml

!include "MUI2.nsh"

; ── Custom pages ──

!macro customInit
  ; Per-user install by default
  StrCpy $INSTDIR "$LOCALAPPDATA\LeAgent"
!macroend

!macro customInstallMode
  ; Allow the user to choose per-user or per-machine
  !insertmacro MUI_PAGE_DIRECTORY
!macroend

; ── Uninstall prompt for user data ──

!macro customUnInit
  ; Nothing extra on uninstall init
!macroend

!macro customRemoveFiles
  ; Ask whether to remove user data
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "Remove LeAgent user data (settings, databases, logs)?$\n$\nUser data location: $APPDATA\LeAgent" \
    IDNO skip_data_removal

  RMDir /r "$APPDATA\LeAgent"
  RMDir /r "$LOCALAPPDATA\LeAgent"

  skip_data_removal:
!macroend
