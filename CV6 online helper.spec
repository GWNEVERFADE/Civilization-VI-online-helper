from PyInstaller.utils.hooks import collect_all

wv_datas, wv_binaries, wv_hidden = collect_all('webview')
pn_datas, pn_binaries, pn_hidden = collect_all('pythonnet')
cl_datas, cl_binaries, cl_hidden = collect_all('clr_loader')

a = Analysis(
    ['G:/CODEX/civ6-l3-discovery-helper/civ6_p2p_helper.py'],
    pathex=[],
    binaries=[
        ('G:/CODEX/civ6-l3-discovery-helper/bin/easytier-core.exe', 'bin'),
        ('G:/CODEX/civ6-l3-discovery-helper/bin/Packet.dll', 'bin'),
        ('G:/CODEX/civ6-l3-discovery-helper/bin/wintun.dll', 'bin'),
    ] + wv_binaries + pn_binaries + cl_binaries,
    datas=[
        ('G:/CODEX/civ6-l3-discovery-helper/civ6_p2p/ui', 'civ6_p2p/ui'),
    ] + wv_datas + pn_datas + cl_datas,
    hiddenimports=[
        'civ6_p2p.glass_gui',
        'civ6_p2p.vps_store',
        'bottle',
        'proxy_tools',
        'cffi',
    ] + wv_hidden + pn_hidden + cl_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CV6 online helper',
    icon='G:/CODEX/civ6-l3-discovery-helper/civ6_p2p/ui/app_icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
