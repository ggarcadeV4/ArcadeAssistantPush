using System;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using Unbroken.LaunchBox.Plugins;

namespace ArcadeAssistant.Plugin
{
  /// <summary>
  /// Main plugin class - implements both system events (startup/shutdown) and menu item (Tools menu)
  /// </summary>
  public class ArcadeAssistantPlugin : ISystemEventsPlugin, ISystemMenuItemPlugin
  {
    public string Name => "G&G Arcade - Arcade Assistant Bridge";

    // ISystemMenuItemPlugin properties
    public string Caption => "G&G Arcade - Arcade Assistant → Ping Bridge";
    public bool ShowInLaunchBox => true;
    public bool ShowInBigBox => true;
    public bool AllowInBigBoxWhenLocked => false;
    public System.Drawing.Image? IconImage => null;

    public void OnEventRaised(string eventType)
    {
      try
      {
        // Start on plugin initialization
        if (eventType == "PluginInitialized" || eventType == "SystemStarted")
        {
          SafeLog("Plugin starting...");
          // Ensure config exists and load desired port
          var cfg = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Plugins", "ArcadeAssistant", "config.json");
          Directory.CreateDirectory(Path.GetDirectoryName(cfg)!);
          if (!File.Exists(cfg))
          {
            File.WriteAllText(cfg, "{\"port\":9999,\"logLevel\":\"info\"}");
            SafeLog("Created default config.json with port 9999");
          }

          int desiredPort = 9999;
          try
          {
            var json = File.ReadAllText(cfg);
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("port", out var pe) && pe.TryGetInt32(out var p) && p > 0 && p < 65536)
            {
              desiredPort = p;
            }
          }
          catch (Exception ex)
          {
            SafeLog("Config parse error; defaulting port 9999. " + ex.Message);
          }

          // Start HTTP bridge with configured port (bridge will fall back if busy)
          SafeLog($"Starting HTTP bridge on desired port {desiredPort}...");
          Bridge.HttpBridge.Start(desiredPort);
          SafeLog("Plugin started successfully.");
        }
        else if (eventType == "LaunchBoxShutdownBeginning" || eventType == "SystemShutdown")
        {
          Bridge.HttpBridge.Stop();
          SafeLog("Plugin stopped successfully.");
        }
      }
      catch (Exception ex) { SafeLog($"Event '{eventType}' error: " + ex); }
    }

    // ISystemMenuItemPlugin method - called when user clicks Tools → Arcade Assistant → Ping Bridge
    public void OnSelected()
    {
      try
      {
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        var port = Bridge.HttpBridge.CurrentPort;
        var uri = new Uri($"http://127.0.0.1:{port}/health");
        var json = http.GetStringAsync(uri).GetAwaiter().GetResult();

        // Pretty print JSON
        try
        {
          var doc = JsonDocument.Parse(json);
          json = JsonSerializer.Serialize(doc, new JsonSerializerOptions { WriteIndented = true });
        }
        catch { /* use raw JSON if parse fails */ }

        MessageBox.Show(
          json,
          "G&G Arcade - Arcade Assistant Bridge",
          MessageBoxButton.OK,
          MessageBoxImage.Information
        );
      }
      catch (Exception ex)
      {
        MessageBox.Show(
          $"Ping failed:\r\n{ex.Message}",
          "G&G Arcade - Arcade Assistant Bridge",
          MessageBoxButton.OK,
          MessageBoxImage.Warning
        );
      }
    }

    private static void SafeLog(string msg)
    {
      try
      {
        // Use portable path - works on any drive where LaunchBox is installed
        var lbRoot = Path.GetDirectoryName(Path.GetDirectoryName(AppDomain.CurrentDomain.BaseDirectory));
        var log = Path.Combine(lbRoot!, "Logs", "ArcadeAssistant.log");
        Directory.CreateDirectory(Path.GetDirectoryName(log)!);
        File.AppendAllText(log, $"[{DateTime.Now:u}] {msg}\r\n");
      }
      catch { /* never crash host */ }
    }
  }
}
