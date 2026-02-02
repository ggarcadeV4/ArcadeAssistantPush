using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Unbroken.LaunchBox.Plugins;

namespace ArcadeAssistant.Plugin
{
  /// <summary>
  /// Safe importer using LaunchBox plugin APIs (no raw XML edits).
  /// </summary>
  public static class Importer
  {
    public static object ListMissing(string platform, string folder)
    {
      var exts = GetExtensionsForPlatform(platform);
      if (exts.Length == 0) throw new ArgumentException($"Unsupported platform: {platform}");
      if (!Directory.Exists(folder)) throw new DirectoryNotFoundException($"Folder not found: {folder}");

      var existing = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
      try
      {
        var all = PluginHelper.DataManager.GetAllGames();
        foreach (var g in all)
        {
          if (g == null) continue;
          if (!string.Equals(g.Platform ?? string.Empty, platform, StringComparison.OrdinalIgnoreCase)) continue;
          var ap = g.ApplicationPath ?? string.Empty;
          if (!string.IsNullOrWhiteSpace(ap)) existing.Add(Path.GetFullPath(ap));
        }
      }
      catch (Exception ex) { SafeLog("Existing scan error: " + ex.Message); }

      var files = new List<object>();
      int existingCount = 0;
      try
      {
        foreach (var path in Directory.EnumerateFiles(folder))
        {
          var ext = Path.GetExtension(path)?.ToLowerInvariant() ?? string.Empty;
          if (!exts.Contains(ext)) continue;
          var full = Path.GetFullPath(path);
          if (existing.Contains(full)) { existingCount++; continue; }
          var name = Path.GetFileNameWithoutExtension(path);
          files.Add(new { path = full, name });
        }
      }
      catch (Exception ex) { SafeLog("Folder scan error: " + ex.Message); }

      return new { platform, folder, missing = files, counts = new { missing = files.Count, existing = existingCount } };
    }

    public static (int added, int skipped, int duplicates, List<object> errors) ImportMissing(string platform, string folder)
    {
      var scanObj = ListMissing(platform, folder);

      int added = 0, skipped = 0, duplicates = 0;
      var errors = new List<object>();

      // Extract anonymous missing list via reflection
      var scanType = scanObj.GetType();
      var missingProp = scanType.GetProperty("missing");
      var missingList = missingProp?.GetValue(scanObj) as IEnumerable;
      if (missingList == null) return (0, 0, 0, errors);

      foreach (var item in missingList)
      {
        try
        {
          var it = item.GetType();
          var path = it.GetProperty("path")?.GetValue(item) as string ?? string.Empty;
          var name = it.GetProperty("name")?.GetValue(item) as string ?? Path.GetFileNameWithoutExtension(path);
          if (string.IsNullOrWhiteSpace(path)) { skipped++; continue; }

          if (TryAddGame(platform, name, path)) { added++; }
          else { skipped++; }
        }
        catch (Exception ex)
        {
          string p = string.Empty;
          try { p = item.GetType().GetProperty("path")?.GetValue(item) as string ?? string.Empty; } catch { }
          errors.Add(new { path = p, error = ex.Message });
        }
      }

      return (added, skipped, duplicates, errors);
    }

    private static string[] GetExtensionsForPlatform(string platform)
    {
      var p = (platform ?? string.Empty).Trim().ToLowerInvariant();
      if (p.Contains("mame") || p.Contains("arcade"))
      {
        return new[] { ".zip", ".7z" };
      }
      if (p.Contains("playstation 2") || p == "ps2" || p.Contains("sony playstation 2"))
      {
        return new[] { ".iso", ".bin", ".cue", ".img", ".chd", ".7z", ".zip", ".gz" };
      }
      return Array.Empty<string>();
    }

    private static bool TryAddGame(string platform, string title, string applicationPath)
    {
      try
      {
        // Normalize title from filename if needed
        if (string.IsNullOrWhiteSpace(title))
        {
          title = Path.GetFileNameWithoutExtension(applicationPath) ?? string.Empty;
        }
        title = title.Replace('_', ' ').Replace('.', ' ').Trim();

        var dm = PluginHelper.DataManager;
        if (dm == null) return false;

        var dmType = dm.GetType();

        // Try common overload: AddNewGame(string title, string appPath, string platform)
        var method = dmType.GetMethod("AddNewGame", new Type[] { typeof(string), typeof(string), typeof(string) });
        if (method != null)
        {
          var res = method.Invoke(dm, new object[] { title, applicationPath, platform });
          return res != null;
        }

        // Fallback: construct IGame-like instance via exemplar type and AddGame(IGame)
        var all = PluginHelper.DataManager.GetAllGames();
        var exemplar = all.FirstOrDefault();
        var gameType = exemplar?.GetType();
        if (gameType != null)
        {
          var newGame = Activator.CreateInstance(gameType);
          gameType.GetProperty("Title")?.SetValue(newGame, title);
          gameType.GetProperty("Platform")?.SetValue(newGame, platform);
          gameType.GetProperty("ApplicationPath")?.SetValue(newGame, applicationPath);

          var add1 = dmType.GetMethods().FirstOrDefault(m => (m.Name == "AddGame" || m.Name == "AddNewGame") && m.GetParameters().Length == 1);
          if (add1 != null)
          {
            var res = add1.Invoke(dm, new object[] { newGame });
            return res != null;
          }
        }
      }
      catch (Exception ex)
      {
        SafeLog("Add game error: " + ex.Message);
      }
      return false;
    }

    private static void SafeLog(string msg)
    {
      try
      {
        var lbRoot = Path.GetDirectoryName(Path.GetDirectoryName(AppDomain.CurrentDomain.BaseDirectory));
        var p = Path.Combine(lbRoot!, "Logs", "ArcadeAssistant.log");
        Directory.CreateDirectory(Path.GetDirectoryName(p)!);
        File.AppendAllText(p, $"[{DateTime.Now:u}] {msg}\r\n");
      } catch { }
    }
  }
}

