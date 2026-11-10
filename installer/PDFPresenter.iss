; Build with Inno Setup 7.1 or newer. No application data is removed on uninstall.
#ifndef AppVersion
  #define AppVersion "2.3.0"
#endif
#ifndef AppName
  #define AppName "Сцена"
#endif
#ifndef AppIdString
  #define AppIdString "{{6578E2F1-8DBE-4F53-B7CD-C865D6AF6509}"
#endif
#ifndef OutputName
  #define OutputName "Scene-Setup-" + AppVersion + "-x64"
#endif
#define AppExeName "PDFPresenter.exe"

[Setup]
AppId={#AppIdString}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Сцена
VersionInfoDescription=Сцена — установщик
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\PDFPresenter
DefaultGroupName={#AppName}
UsePreviousGroup=no
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename={#OutputName}
SetupIconFile=..\src\pdf_presenter\resources\icons\scene.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dynamic
DisableWelcomePage=no
UsePreviousAppDir=yes
UsePreviousTasks=yes
CloseApplications=yes
CloseApplicationsFilter=PDFPresenter.exe
RestartApplications=no
UninstallDisplayName={#AppName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PDFPresenter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; AppUserModelID: "PDFPresenter.Desktop.1"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; AppUserModelID: "PDFPresenter.Desktop.1"; Tasks: desktopicon

#ifndef VerificationBuild
; Replace only shortcuts created under the previous product name on upgrade.
[InstallDelete]
Type: files; Name: "{userprograms}\PDF Presenter\PDF Presenter.lnk"
Type: dirifempty; Name: "{userprograms}\PDF Presenter"
Type: files; Name: "{userdesktop}\PDF Presenter.lnk"
#endif

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
