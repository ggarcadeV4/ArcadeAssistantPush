using System;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using Unbroken.LaunchBox.Plugins;
using Unbroken.LaunchBox.Plugins.Data;

namespace ArcadeAssistant.Plugin
{
  /// <summary>
  /// Main plugin class - implements system events (startup/shutdown),
  /// game lifecycle events (launch/exit), and menu item (Tools menu).
  /// </summary>
  public class ArcadeAssistantPlugin : ISystemEventsPlugin, ISystemMenuItemPlugin, IGameLaunchingPlugin
  {
    public string Name => "G&G Arcade - Arcade Assistant Bridge";

    // ISystemMenuItemPlugin properties
    public string Caption => "G&G Arcade - Arcade Assistant → Ping Bridge";
    public bool ShowInLaunchBox => true;
    public bool ShowInBigBox => true;
    public bool AllowInBigBoxWhenLocked => false;
    public System.Drawing.Image? IconImage => null;

    // Shared HttpClient for backend notifications (reusable, thread-safe)
    private static readonly HttpClient _backendHttp = new HttpClient
    {
      BaseAddress = new Uri("http://127.0.0.1:8000"),
      Timeout = TimeSpan.FromSeconds(3)
    };

    // Cache the last launched game so OnGameExited() can reference it
    private static IGame? _lastLaunchedGame;

    // ----------------------------------------------------------------
    // ISystemEventsPlugin
    // ----------------------------------------------------------------

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

    // ----------------------------------------------------------------
    // IGameLaunchingPlugin — Game Lifecycle Events
    // ----------------------------------------------------------------

    public void OnBeforeGameLaunching(IGame game, IAdditionalApplication app, IEmulator emulator)
    {
      // No action before launch — we notify after successful launch
    }

    public void OnAfterGameLaunched(IGame game, IAdditionalApplication app, IEmulator emulator)
    {
      // Cache game for OnGameExited (which receives no parameters)
      _lastLaunchedGame = game;

      if (game == null) return;

      // Fire-and-forget POST to backend — never block the game launch
      _ = Task.Run(async () =>
      {
        try
        {
          var payload = new
          {
            game_id = game.Id,
            platform = game.Platform,
            title = game.Title,
            source = "launchbox",
            timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
          };

          var json = JsonSerializer.Serialize(payload);
          var content = new StringContent(json, Encoding.UTF8, "application/json");
          var response = await _backendHttp.PostAsync("/api/game/start", content);

          SafeLog($"Game start notified: '{game.Title}' (HTTP {(int)response.StatusCode})");
        }
        catch (Exception ex)
        {
          // Silent failure — backend may not be running; game must launch normally
          SafeLog($"Game start notify failed (non-fatal): {ex.Message}");
        }
      });
    }

    public void OnGameExited()
    {
      var game = _lastLaunchedGame;
      _lastLaunchedGame = null;

      // Fire-and-forget POST to backend
      _ = Task.Run(async () =>
      {
        try
        {
          var payload = new
          {
            game_id = game?.Id,
            title = game?.Title,
            source = "launchbox",
            timestamp = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
          };

          var json = JsonSerializer.Serialize(payload);
          var content = new StringContent(json, Encoding.UTF8, "application/json");
          var response = await _backendHttp.PostAsync("/api/game/stop", content);

          SafeLog($"Game exit notified: '{game?.Title ?? "unknown"}' (HTTP {(int)response.StatusCode})");
        }
        catch (Exception ex)
        {
          // Silent failure — backend may not be running
          SafeLog($"Game exit notify failed (non-fatal): {ex.Message}");
        }
      });
    }

    // ----------------------------------------------------------------
    // ISystemMenuItemPlugin — Tools menu ping
    // ----------------------------------------------------------------

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

    // ----------------------------------------------------------------
    // Logging
    // ----------------------------------------------------------------

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
