; LiteRetail installer additions (included by electron-builder, see electron-builder.yml nsis.include).
;
; Pages added after "Choose install location":
;   1. Setup type        Main PC (server) / Counter PC
;   2. Main PC only      PostgreSQL found  -> host, port, superuser, password (tested with psql)
;                        PostgreSQL absent -> choose the superuser password; the bundled installer runs silently
;   3. Counter PC only   server IP + counter code
; After the files are copied (customInstall):
;   Main PC    install PostgreSQL if needed -> literetailer-backend setup (role, database, backend.env, migrations,
;              store "My Store", counters C01-C05, admin / admin123) -> Windows service -> firewall port 5000
;              -> scheduled tasks (WhatsApp daily collection every 15 min, e-bill retry every 5 min)
;   Both       literetailer-backend write-counter -> C:\ProgramData\LiteRetailer\counter.json
; The shop licence is kept by the server on the Main PC (license.json there) and shared by every counter.
; The database and C:\ProgramData\LiteRetailer are never deleted by the uninstaller.

!include nsDialogs.nsh
!include LogicLib.nsh
!include MUI2.nsh

!define SERVICE_NAME "LiteRetailerServer"
!define FIREWALL_RULE "LiteRetail Server"
!define APP_PORT "5000"
; Task Scheduler jobs on the Main PC (run as SYSTEM, output in C:\ProgramData\LiteRetailer\logs\<command>.log)
!define TASK_DAILY "LiteRetail Daily Collection"
!define TASK_EBILLS "LiteRetail E-bill Retry"
; Bundled PostgreSQL installer (download once into build\vendor\postgresql, see scripts\build\build_installer.ps1).
!define PG_INSTALLER "postgresql-17.6-1-windows-x64.exe"

; Stop the running service before files are replaced (upgrade / repair).
!macro customInit
  nsExec::Exec 'sc.exe stop ${SERVICE_NAME}'
  Pop $0
  ${If} $0 == 0
    Sleep 4000
  ${EndIf}
!macroend

!macro customUnInit
  nsExec::Exec 'sc.exe stop ${SERVICE_NAME}'
  Pop $0
  ${If} $0 == 0
    Sleep 4000
  ${EndIf}
!macroend

!macro customUnInstall
  nsExec::Exec 'sc.exe delete ${SERVICE_NAME}'
  Pop $0
  nsExec::Exec 'schtasks.exe /Delete /F /TN "${TASK_DAILY}"'
  Pop $0
  nsExec::Exec 'schtasks.exe /Delete /F /TN "${TASK_EBILLS}"'
  Pop $0
  nsExec::Exec 'netsh advfirewall firewall delete rule name="${FIREWALL_RULE}"'
  Pop $0
!macroend

!ifndef BUILD_UNINSTALLER

Var SetupType      ; "server" or "counter"
Var PgFound        ; 1 = a PostgreSQL server is already on this PC
Var PgBase         ; its install folder (for psql.exe), may be empty
Var PgHost
Var PgPort
Var PgUser
Var PgPass
Var ServerIp
Var CounterCode
Var hRadioServer
Var hRadioCounter
Var hHost
Var hPort
Var hUser
Var hPass
Var hPass2
Var hServerIp
Var hCounterCode

!macro customPageAfterChangeDir
  Page custom SetupTypePageCreate SetupTypePageLeave
  Page custom PgPageCreate PgPageLeave
  Page custom CounterPageCreate CounterPageLeave
!macroend

; ------------------------------------------------------------------ page 1: setup type

Function SetupTypePageCreate
  ${If} $SetupType == ""
    StrCpy $SetupType "server"
    StrCpy $PgHost "localhost"
    StrCpy $PgPort "5432"
    StrCpy $PgUser "postgres"
    StrCpy $CounterCode "C02"
    Call DetectPostgres
  ${EndIf}

  !insertmacro MUI_HEADER_TEXT "Setup type" "How will this PC be used?"
  nsDialogs::Create 1018
  Pop $0

  ${NSD_CreateRadioButton} 0 6u 100% 12u "Main PC (server)"
  Pop $hRadioServer
  ${NSD_CreateLabel} 14u 20u 95% 24u "Installs the database and the LiteRetail server on this PC. Choose this on the store's first (or only) PC."
  Pop $0

  ${NSD_CreateRadioButton} 0 52u 100% 12u "Counter PC"
  Pop $hRadioCounter
  ${NSD_CreateLabel} 14u 66u 95% 24u "Only the billing app. It connects to the Main PC over the store network."
  Pop $0

  ${If} $SetupType == "counter"
    ${NSD_Check} $hRadioCounter
  ${Else}
    ${NSD_Check} $hRadioServer
  ${EndIf}
  nsDialogs::Show
FunctionEnd

Function SetupTypePageLeave
  ${NSD_GetState} $hRadioCounter $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $SetupType "counter"
  ${Else}
    StrCpy $SetupType "server"
  ${EndIf}
FunctionEnd

; Finds an existing PostgreSQL: the EnterpriseDB installer's registry keys, or anything listening on 5432.
Function DetectPostgres
  StrCpy $PgFound 0
  StrCpy $PgBase ""
  SetRegView 64
  EnumRegKey $0 HKLM "SOFTWARE\PostgreSQL\Installations" 0
  ${If} $0 != ""
    ReadRegStr $PgBase HKLM "SOFTWARE\PostgreSQL\Installations\$0" "Base Directory"
    StrCpy $PgFound 1
  ${EndIf}
  EnumRegKey $0 HKLM "SOFTWARE\PostgreSQL\Services" 0
  ${If} $0 != ""
    ReadRegDWORD $1 HKLM "SOFTWARE\PostgreSQL\Services\$0" "Port"
    ${If} $1 != ""
      StrCpy $PgPort $1
    ${EndIf}
    StrCpy $PgFound 1
  ${EndIf}
  SetRegView lastused
  ${If} $PgFound == 0
    nsExec::ExecToStack 'powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"'
    Pop $0
    Pop $1
    ${If} $0 == 0
      StrCpy $PgFound 1
    ${EndIf}
  ${EndIf}
FunctionEnd

; ------------------------------------------------------------------ page 2: PostgreSQL (Main PC)

Function PgPageCreate
  ${If} $SetupType != "server"
    Abort ; skip this page
  ${EndIf}

  nsDialogs::Create 1018
  Pop $0

  ${If} $PgFound == 1
    !insertmacro MUI_HEADER_TEXT "Database" "PostgreSQL is already installed on this PC. Enter its administrator login."
    ${NSD_CreateLabel} 0 0 100% 20u "LiteRetail will create its own database (literetailer_db) and database user on this server. The administrator password is only used now and is not saved."
    Pop $0
    ${NSD_CreateLabel} 0 28u 30% 12u "Host"
    Pop $0
    ${NSD_CreateText} 32% 26u 50% 12u $PgHost
    Pop $hHost
    ${NSD_CreateLabel} 0 46u 30% 12u "Port"
    Pop $0
    ${NSD_CreateNumber} 32% 44u 20% 12u $PgPort
    Pop $hPort
    ${NSD_CreateLabel} 0 64u 30% 12u "Administrator user"
    Pop $0
    ${NSD_CreateText} 32% 62u 50% 12u $PgUser
    Pop $hUser
    ${NSD_CreateLabel} 0 82u 30% 12u "Password"
    Pop $0
    ${NSD_CreatePassword} 32% 80u 50% 12u $PgPass
    Pop $hPass
  ${Else}
    !insertmacro MUI_HEADER_TEXT "Database" "PostgreSQL 17 will be installed on this PC."
    ${NSD_CreateLabel} 0 0 100% 28u "Choose the password for the PostgreSQL administrator (user 'postgres'). Write it down: it is needed for database maintenance and when you reinstall or upgrade LiteRetail."
    Pop $0
    ${NSD_CreateLabel} 0 36u 30% 12u "Password"
    Pop $0
    ${NSD_CreatePassword} 32% 34u 50% 12u $PgPass
    Pop $hPass
    ${NSD_CreateLabel} 0 54u 30% 12u "Confirm password"
    Pop $0
    ${NSD_CreatePassword} 32% 52u 50% 12u $PgPass
    Pop $hPass2
    ${NSD_CreateLabel} 0 72u 30% 12u "Port"
    Pop $0
    ${NSD_CreateNumber} 32% 70u 20% 12u $PgPort
    Pop $hPort
  ${EndIf}
  nsDialogs::Show
FunctionEnd

Function PgPageLeave
  ${NSD_GetText} $hPass $PgPass
  ${NSD_GetText} $hPort $PgPort
  ${If} $PgPort == ""
    StrCpy $PgPort "5432"
  ${EndIf}
  Push $PgPass
  Call CheckPasswordChars
  Pop $0
  ${If} $0 != "ok"
    MessageBox MB_ICONEXCLAMATION $0
    Abort
  ${EndIf}

  ${If} $PgFound == 1
    ${NSD_GetText} $hHost $PgHost
    ${NSD_GetText} $hUser $PgUser
    ${If} $PgHost == ""
    ${OrIf} $PgUser == ""
      MessageBox MB_ICONEXCLAMATION "Enter the host and the administrator user."
      Abort
    ${EndIf}
    ; Test the login with the existing installation's psql.exe (the app files are not copied yet).
    ${If} ${FileExists} "$PgBase\bin\psql.exe"
      System::Call 'Kernel32::SetEnvironmentVariable(t "PGPASSWORD", t "$PgPass")i'
      System::Call 'Kernel32::SetEnvironmentVariable(t "PGCONNECT_TIMEOUT", t "10")i'
      nsExec::ExecToStack '"$PgBase\bin\psql.exe" -w -h "$PgHost" -p $PgPort -U "$PgUser" -d postgres -t -c "select 1"'
      Pop $0
      Pop $1
      System::Call 'Kernel32::SetEnvironmentVariable(t "PGPASSWORD", p 0)i'
      ${If} $0 != 0
        MessageBox MB_ICONSTOP "Cannot connect to PostgreSQL with these details:$\r$\n$\r$\n$1"
        Abort
      ${EndIf}
    ${EndIf}
  ${Else}
    ${NSD_GetText} $hPass2 $0
    ${If} $PgPass != $0
      MessageBox MB_ICONEXCLAMATION "The two passwords are different."
      Abort
    ${EndIf}
    StrLen $0 $PgPass
    ${If} $0 < 6
      MessageBox MB_ICONEXCLAMATION "Use at least 6 characters for the password."
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

; Passwords go on a command line, so quotes and spaces are not allowed. Pushes "ok" or an error message.
Function CheckPasswordChars
  Exch $0 ; password
  Push $1
  Push $2
  ${If} $0 == ""
    StrCpy $0 "Enter the password."
    Goto done
  ${EndIf}
  StrCpy $1 0
  loop:
    StrCpy $2 $0 1 $1
    ${If} $2 == ""
      StrCpy $0 "ok"
      Goto done
    ${EndIf}
    ${If} $2 == '"'
    ${OrIf} $2 == " "
    ${OrIf} $2 == "%"
      StrCpy $0 "The password cannot contain spaces, double quotes or %."
      Goto done
    ${EndIf}
    IntOp $1 $1 + 1
    Goto loop
  done:
  Pop $2
  Pop $1
  Exch $0
FunctionEnd

; ------------------------------------------------------------------ page 3: Counter PC

Function CounterPageCreate
  ${If} $SetupType != "counter"
    Abort ; skip this page
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "Counter" "Connect this counter to the Main PC."
  nsDialogs::Create 1018
  Pop $0
  ${NSD_CreateLabel} 0 0 100% 20u "Enter the Main PC's IP address on the store network (on the Main PC run 'ipconfig' and use its IPv4 address, e.g. 192.168.1.10)."
  Pop $0
  ${NSD_CreateLabel} 0 30u 30% 12u "Main PC IP address"
  Pop $0
  ${NSD_CreateText} 32% 28u 50% 12u $ServerIp
  Pop $hServerIp
  ${NSD_CreateLabel} 0 48u 30% 12u "Counter code"
  Pop $0
  ${NSD_CreateDropList} 32% 46u 20% 60u ""
  Pop $hCounterCode
  ${NSD_CB_AddString} $hCounterCode "C02"
  ${NSD_CB_AddString} $hCounterCode "C03"
  ${NSD_CB_AddString} $hCounterCode "C04"
  ${NSD_CB_AddString} $hCounterCode "C05"
  ${NSD_CB_SelectString} $hCounterCode $CounterCode
  ${NSD_CreateLabel} 0 66u 100% 28u "Each counter PC needs a different code. C01 is the Main PC. More counters can be added in LiteRetail under Admin > Counters."
  Pop $0
  nsDialogs::Show
FunctionEnd

Function CounterPageLeave
  ${NSD_GetText} $hServerIp $ServerIp
  ${NSD_GetText} $hCounterCode $CounterCode
  ${If} $ServerIp == ""
    MessageBox MB_ICONEXCLAMATION "Enter the Main PC's IP address."
    Abort
  ${EndIf}
  Push $ServerIp
  Call CheckPasswordChars ; same rule: no spaces / quotes
  Pop $0
  ${If} $0 != "ok"
    MessageBox MB_ICONEXCLAMATION "The IP address cannot contain spaces or quotes."
    Abort
  ${EndIf}
FunctionEnd

; ------------------------------------------------------------------ install steps

!macro customInstall
  StrCpy $R9 "$INSTDIR\resources\backend\literetailer-backend.exe"
  ReadEnvStr $R8 "ProgramData"
  StrCpy $R8 "$R8\LiteRetailer"
  CreateDirectory "$R8\logs"

  ${If} ${Silent}
    ; Silent update: keep the existing setup, just bring the service back.
    ${If} ${FileExists} "$R8\backend.env"
      nsExec::Exec '"$INSTDIR\resources\backend\winsw\${SERVICE_NAME}.exe" install'
      Pop $0
      nsExec::Exec 'sc.exe start ${SERVICE_NAME}'
      Pop $0
    ${EndIf}
  ${Else}
    ${If} $SetupType == "server"
      ${If} $PgFound == 0
        DetailPrint "Installing PostgreSQL 17 (this takes a few minutes)..."
        InitPluginsDir
        SetOutPath "$PLUGINSDIR"
        File "/oname=$PLUGINSDIR\${PG_INSTALLER}" "${BUILD_RESOURCES_DIR}\vendor\postgresql\${PG_INSTALLER}"
        ExecWait '"$PLUGINSDIR\${PG_INSTALLER}" --mode unattended --unattendedmodeui minimal --superpassword "$PgPass" --serverport $PgPort --disable-components pgAdmin,stackbuilder' $0
        Delete "$PLUGINSDIR\${PG_INSTALLER}"
        SetOutPath "$INSTDIR"
        ${If} $0 != 0
          MessageBox MB_ICONSTOP "PostgreSQL could not be installed (error $0). Run this installer again."
          Abort
        ${EndIf}
        StrCpy $PgHost "localhost"
        StrCpy $PgUser "postgres"
      ${EndIf}

      DetailPrint "Creating the LiteRetail database..."
      nsExec::ExecToStack '"$R9" setup --host "$PgHost" --port $PgPort --superuser "$PgUser" --superpassword "$PgPass" --app-port ${APP_PORT}'
      Pop $0
      Pop $1
      DetailPrint $1
      ${If} $0 != 0
        MessageBox MB_ICONSTOP "The LiteRetail database could not be set up:$\r$\n$\r$\n$1$\r$\nDetails: $R8\logs\setup.log"
        Abort
      ${EndIf}

      ; Only administrators and the service (SYSTEM) may read the database password and secrets.
      nsExec::Exec 'icacls "$R8\backend.env" /inheritance:r /grant:r *S-1-5-18:F *S-1-5-32-544:F'
      Pop $0

      DetailPrint "Installing the LiteRetail Server service..."
      nsExec::Exec 'sc.exe delete ${SERVICE_NAME}'
      Pop $0
      nsExec::ExecToStack '"$INSTDIR\resources\backend\winsw\${SERVICE_NAME}.exe" install'
      Pop $0
      Pop $1
      nsExec::ExecToStack 'sc.exe start ${SERVICE_NAME}'
      Pop $0
      Pop $1

      ; Counter PCs reach the server on port 5000.
      nsExec::Exec 'netsh advfirewall firewall delete rule name="${FIREWALL_RULE}"'
      Pop $0
      nsExec::Exec 'netsh advfirewall firewall add rule name="${FIREWALL_RULE}" dir=in action=allow protocol=TCP localport=${APP_PORT}'
      Pop $0

      ; WhatsApp daily collection summary (sends once the time set in Admin > Settings has passed)
      ; and retries of e-bills that failed when the bill was paid.
      DetailPrint "Registering scheduled tasks..."
      nsExec::Exec 'schtasks.exe /Create /F /RU SYSTEM /RL HIGHEST /SC MINUTE /MO 15 /TN "${TASK_DAILY}" /TR "\"$R9\" task send-daily-collection"'
      Pop $0
      nsExec::Exec 'schtasks.exe /Create /F /RU SYSTEM /RL HIGHEST /SC MINUTE /MO 5 /TN "${TASK_EBILLS}" /TR "\"$R9\" task send-ebills"'
      Pop $0

      StrCpy $CounterCode "C01"
      StrCpy $ServerIp "localhost"
    ${EndIf}

    nsExec::ExecToStack '"$R9" write-counter --code $CounterCode --api-url "http://$ServerIp:${APP_PORT}/api/v1"'
    Pop $0
    Pop $1
    DetailPrint $1
    ; Every Windows user may save printer settings into counter.json.
    nsExec::Exec 'icacls "$R8\counter.json" /grant *S-1-5-32-545:M'
    Pop $0
  ${EndIf}
!macroend

!endif
