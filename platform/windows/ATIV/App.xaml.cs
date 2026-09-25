// SPDX-FileCopyrightText: Thomas Lothian
// SPDX-License-Identifier: GPL-3.0-or-later
using Microsoft.UI.Xaml;
using System.Runtime.InteropServices;

namespace ATIV;

public partial class App : Application
{
    private Window? window;

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

    public App() {
        var development = File.Exists(Path.Combine(AppContext.BaseDirectory,"development-build"));
        Marshal.ThrowExceptionForHR(SetCurrentProcessExplicitAppUserModelID(development ? "com.tlolabs.ativ.development" : "com.tlolabs.ativ"));
        InitializeComponent();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        window = new MainWindow();
        window.Activate();
    }
}
