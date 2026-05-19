; LeAgent NSIS custom installer hooks
; Included by electron-builder via nsis.include in electron-builder.yml
;
; NOTE: Do NOT !include "MUI2.nsh" here — electron-builder's own NSIS
; scaffolding already includes it, and a second include causes conflicts.
; Likewise, do NOT insert MUI_PAGE_DIRECTORY inside customInstallMode;
; electron-builder's assisted installer adds that page automatically when
; allowToChangeInstallationDirectory is true in electron-builder.yml.

; ── Custom pages ──

!macro customInit
  ; Per-user install by default
  StrCpy $INSTDIR "$LOCALAPPDATA\LeAgent"
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
