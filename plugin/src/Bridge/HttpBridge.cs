using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace ArcadeAssistant.Plugin.Bridge
{
  public static class HttpBridge
  {
    private static HttpListener? _listener;
    private static Thread? _thread;
    private static CancellationTokenSource? _cts;
    private static int _port = 9999;
    private static readonly int _fallbackPort = 10099;
    private static readonly HttpClient _httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };

    /// <summary>
    /// Gets the current active port (reflects fallback if primary port was unavailable)
    /// </summary>
    public static int CurrentPort => _port;

    public static void Start(int? desiredPort = null)
    {
      if (_listener != null) return;
      try
      {
        _cts = new CancellationTokenSource();
        _listener = new HttpListener();

        _port = desiredPort.HasValue ? desiredPort.Value : 9999;
        if (!TryStartListener(_port))
        {
          Log($"Port {_port} unavailable; attempting fallback port {_fallbackPort}...");
          if (!TryStartListener(_fallbackPort))
          {
            throw new InvalidOperationException($"Unable to start HTTP bridge on {_port} or {_fallbackPort}");
          }
          _port = _fallbackPort;
        }

        _thread = new Thread(() => Loop(_cts!.Token)) { IsBackground = true, Name = "AA.HttpBridge" };
        _thread.Start();
        Log("HTTP bridge started on port " + _port);
      }
      catch (Exception ex)
      {
        Log("HTTP start error: " + ex);
        // Ensure cleanup if start fails
        try { _listener?.Close(); } catch { }
        _listener = null;
      }
    }

    public static void Stop()
    {
      try { _cts?.Cancel(); } catch { }
      try { _listener?.Stop(); } catch { }
      try { _listener?.Close(); } catch { }
      try { if (_thread != null && _thread.IsAlive) { if (!_thread.Join(TimeSpan.FromSeconds(2))) { Log("HTTP bridge thread did not stop within timeout."); } } } catch { }
      _listener = null;
      _thread = null;
      _cts = null;
      Log("HTTP bridge stopped.");
    }

    private static void Loop(CancellationToken ct)
    {
      while (!ct.IsCancellationRequested && _listener != null && _listener.IsListening)
      {
        HttpListenerContext ctx;
        try { ctx = _listener.GetContext(); }
        catch { if (ct.IsCancellationRequested) break; else continue; }

        try { Handle(ctx); }
        catch (Exception ex) { Log("Handler error: " + ex); TryWrite(ctx, 500, Json(new { error = "internal_error" })); }
      }
    }

    private static void Handle(HttpListenerContext ctx)
    {
      var method = ctx.Request.HttpMethod ?? "";
      var path = ctx.Request.Url!.AbsolutePath.TrimEnd('/').ToLowerInvariant();
      Log($"Request: {method} {path}");

      if (ctx.Request.HttpMethod == "GET" && path == "/health")
      {
        TryWrite(ctx, 200, Json(new { status = "ok", plugin = "Arcade Assistant Bridge", port = _port, version = "1.0.0" }));
        return;
      }

      if (ctx.Request.HttpMethod == "POST" && path == "/launch")
      {
        try
        {
          // Read POST body
          string body;
          using (var reader = new StreamReader(ctx.Request.InputStream, ctx.Request.ContentEncoding))
          {
            body = reader.ReadToEnd();
          }

          // Parse JSON to get title or id
          string? gameTitle = null;
          string? gameId = null;
          try
          {
            var doc = JsonDocument.Parse(body);
            if (doc.RootElement.TryGetProperty("title", out var titleProp))
            {
              gameTitle = titleProp.GetString();
            }
            if (doc.RootElement.TryGetProperty("id", out var idProp))
            {
              gameId = idProp.GetString();
            }
          }
          catch (Exception ex)
          {
            Log($"Failed to parse launch request: {ex.Message}");
            TryWrite(ctx, 400, Json(new { success = false, error = "Invalid JSON" }));
            return;
          }

          Unbroken.LaunchBox.Plugins.Data.IGame? matchingGame = null;

          // Try to find game by ID first (more precise)
          if (!string.IsNullOrWhiteSpace(gameId))
          {
            Log($"Launch request by ID: {gameId}");

            // Check rate limit
            if (IsLaunchThrottled(gameId))
            {
              TryWrite(ctx, 429, Json(new { success = false, error = "Launch request throttled - please wait before retrying" }));
              return;
            }

            matchingGame = Unbroken.LaunchBox.Plugins.PluginHelper.DataManager.GetGameById(gameId);

            if (matchingGame == null)
            {
              Log($"Game not found by ID: {gameId}");
              TryWrite(ctx, 404, Json(new { success = false, error = $"Game with ID '{gameId}' not found" }));
              return;
            }
          }
          // Otherwise search by title
          else if (!string.IsNullOrWhiteSpace(gameTitle))
          {
            Log($"Launch request by title: {gameTitle}");
            var allGames = Unbroken.LaunchBox.Plugins.PluginHelper.DataManager.GetAllGames();
            matchingGame = allGames.FirstOrDefault(g =>
              g.Title?.Equals(gameTitle, StringComparison.OrdinalIgnoreCase) == true);

            if (matchingGame == null)
            {
              Log($"Game not found by title: {gameTitle}");
              TryWrite(ctx, 404, Json(new { success = false, error = $"Game '{gameTitle}' not found" }));
              return;
            }

            // Check rate limit after finding the game
            if (IsLaunchThrottled(matchingGame.Id))
            {
              TryWrite(ctx, 429, Json(new { success = false, error = "Launch request throttled - please wait before retrying" }));
              return;
            }
          }
          else
          {
            TryWrite(ctx, 400, Json(new { success = false, error = "Either 'title' or 'id' is required" }));
            return;
          }

          Log($"Found game: {matchingGame.Title} (ID: {matchingGame.Id}, Platform: {matchingGame.Platform})");

          // Launch the game using LaunchBoxMainViewModel
          Unbroken.LaunchBox.Plugins.PluginHelper.LaunchBoxMainViewModel.PlayGame(matchingGame, null, null, string.Empty);

          // B2 FIX: Notify Python backend of game start (fire-and-forget)
          _ = Task.Run(() => NotifyBackendGameStart(matchingGame.Id, matchingGame.Platform, matchingGame.Title));

          Log($"Successfully launched: {matchingGame.Title}");
          TryWrite(ctx, 200, Json(new {
            success = true,
            message = $"Launched {matchingGame.Title}",
            game = new {
              id = matchingGame.Id,
              title = matchingGame.Title,
              platform = matchingGame.Platform
            }
          }));
        }
        catch (Exception ex)
        {
          Log($"Launch error: {ex}");
          TryWrite(ctx, 500, Json(new { success = false, error = $"Launch failed: {ex.Message}" }));
        }
        return;
      }

      if (ctx.Request.HttpMethod == "GET" && path == "/search-game")
      {
        try
        {
          // Get title query parameter
          var title = ctx.Request.QueryString["title"];

          if (string.IsNullOrWhiteSpace(title))
          {
            TryWrite(ctx, 400, Json(new { error = "Missing 'title' query parameter" }));
            return;
          }

          Log($"Search request for: {title}");

          // Use GameLauncher for consistent search logic
          var matches = GameLauncher.SearchGames(title);

          Log($"Found {matches.Count} games matching '{title}'");
          TryWrite(ctx, 200, Json(matches));
        }
        catch (Exception ex)
        {
          Log($"Search error: {ex}");
          TryWrite(ctx, 500, Json(new { error = $"Search failed: {ex.Message}" }));
        }
        return;
      }

      if (ctx.Request.HttpMethod == "GET" && path == "/list-platforms")
      {
        try
        {
          Log("List platforms request");
          var platforms = GameLauncher.ListPlatforms();
          Log($"Returning {platforms.Count} platforms");
          TryWrite(ctx, 200, Json(platforms));
        }
        catch (Exception ex)
        {
          Log($"List platforms error: {ex}");
          TryWrite(ctx, 500, Json(new { error = $"List platforms failed: {ex.Message}" }));
        }
        return;
      }

      // -------------------- Import: List Missing --------------------
      if (ctx.Request.HttpMethod == "GET" && path == "/import/missing")
      {
        try
        {
          var platform = ctx.Request.QueryString["platform"] ?? string.Empty;
          var folder = ctx.Request.QueryString["folder"] ?? string.Empty;
          if (string.IsNullOrWhiteSpace(platform) || string.IsNullOrWhiteSpace(folder))
          {
            TryWrite(ctx, 400, Json(new { error = "Missing 'platform' or 'folder'" }));
            return;
          }

          var scan = ArcadeAssistant.Plugin.Importer.ListMissing(platform, folder);
          TryWrite(ctx, 200, Json(scan));
        }
        catch (Exception ex)
        {
          Log($"List missing error: {ex}");
          TryWrite(ctx, 500, Json(new { error = $"List missing failed: {ex.Message}" }));
        }
        return;
      }

      // -------------------- Import: Apply Missing --------------------
      if (ctx.Request.HttpMethod == "POST" && path == "/import/apply")
      {
        try
        {
          string body;
          using (var reader = new StreamReader(ctx.Request.InputStream, ctx.Request.ContentEncoding))
          { body = reader.ReadToEnd(); }
          string platform = string.Empty, folder = string.Empty;
          try
          {
            var doc = JsonDocument.Parse(body);
            if (doc.RootElement.TryGetProperty("platform", out var p)) platform = p.GetString() ?? string.Empty;
            if (doc.RootElement.TryGetProperty("folder", out var f)) folder = f.GetString() ?? string.Empty;
          }
          catch (Exception ex)
          {
            TryWrite(ctx, 400, Json(new { error = $"Invalid JSON: {ex.Message}" }));
            return;
          }

          if (string.IsNullOrWhiteSpace(platform) || string.IsNullOrWhiteSpace(folder))
          {
            TryWrite(ctx, 400, Json(new { error = "Missing 'platform' or 'folder'" }));
            return;
          }

          var result = ArcadeAssistant.Plugin.Importer.ImportMissing(platform, folder);
          Log($"import: platform={platform} added={result.added} skipped={result.skipped} folder={folder}");
          TryWrite(ctx, 200, Json(new { platform, folder, result.added, result.skipped, result.duplicates, errors = result.errors }));
        }
        catch (Exception ex)
        {
          Log($"Import apply error: {ex}");
          TryWrite(ctx, 500, Json(new { error = $"Import failed: {ex.Message}" }));
        }
        return;
      }

      // -------------------- Scores & Events Endpoints --------------------
      if (path == "/scores/by-game" && ctx.Request.HttpMethod == "GET")
      {
        try
        {
          var gameId = ctx.Request.QueryString["gameId"];
          if (string.IsNullOrWhiteSpace(gameId))
          {
            TryWrite(ctx, 400, Json(new { error = "Missing 'gameId'" }));
            return;
          }

          var stats = AggregateScoresByGame(gameId);
          TryWrite(ctx, 200, Json(new {
            success = true,
            gameId = gameId,
            bestScore = stats.bestScore,
            bestPlayer = stats.bestPlayer,
            attempts = stats.attempts,
            lastUpdated = stats.lastUpdated?.ToString("o")
          }));
        }
        catch (Exception ex)
        {
          Log("Scores by-game error: " + ex);
          TryWrite(ctx, 500, Json(new { success = false, error = ex.Message }));
        }
        return;
      }

      if (path == "/scores/leaderboard" && ctx.Request.HttpMethod == "GET")
      {
        try
        {
          int limit = 10;
          var limitStr = ctx.Request.QueryString["limit"];
          if (!string.IsNullOrWhiteSpace(limitStr)) int.TryParse(limitStr, out limit);

          var top = AggregateLeaderboard(limit);
          TryWrite(ctx, 200, Json(new { success = true, leaderboard = top }));
        }
        catch (Exception ex)
        {
          Log("Leaderboard error: " + ex);
          TryWrite(ctx, 500, Json(new { success = false, error = ex.Message }));
        }
        return;
      }

      if (path == "/scores/submit" && ctx.Request.HttpMethod == "POST")
      {
        try
        {
          var body = ReadBody(ctx);
          var doc = JsonDocument.Parse(body);
          var root = doc.RootElement;
          var gameId = root.GetProperty("gameId").GetString();
          var player = root.TryGetProperty("player", out var p) ? p.GetString() : "unknown";
          long score = root.TryGetProperty("score", out var s) ? s.GetInt64() : 0;
          var source = root.TryGetProperty("source", out var so) ? so.GetString() : "manual";
          var title = root.TryGetProperty("title", out var t) ? t.GetString() : null;
          if (string.IsNullOrWhiteSpace(gameId)) { TryWrite(ctx, 400, Json(new { success=false, error = "Missing gameId" })); return; }

          AppendJsonLine(GetScoresPath(), new {
            ts = DateTime.UtcNow.ToString("o"),
            gameId = gameId,
            title = title,
            player = player,
            score = score,
            source = source
          });

          TryWrite(ctx, 200, Json(new { success = true }));
        }
        catch (Exception ex)
        {
          Log("Scores submit error: " + ex);
          TryWrite(ctx, 500, Json(new { success = false, error = ex.Message }));
        }
        return;
      }

      if (path == "/events/launch-start" && ctx.Request.HttpMethod == "POST")
      {
        try
        {
          var body = ReadBody(ctx);
          AppendJsonLine(GetEventsPath(), new { ts = DateTime.UtcNow.ToString("o"), type = "launch_start", body });
          TryWrite(ctx, 200, Json(new { success = true }));
        }
        catch (Exception ex)
        {
          Log("Launch-start error: " + ex);
          TryWrite(ctx, 500, Json(new { success = false, error = ex.Message }));
        }
        return;
      }

      if (path == "/events/launch-end" && ctx.Request.HttpMethod == "POST")
      {
        try
        {
          var body = ReadBody(ctx);
          AppendJsonLine(GetEventsPath(), new { ts = DateTime.UtcNow.ToString("o"), type = "launch_end", body });
          TryWrite(ctx, 200, Json(new { success = true }));
        }
        catch (Exception ex)
        {
          Log("Launch-end error: " + ex);
          TryWrite(ctx, 500, Json(new { success = false, error = ex.Message }));
        }
        return;
      }

      if (ctx.Request.HttpMethod == "GET" && path == "/list-genres")
      {
        try
        {
          Log("List genres request");
          var genres = GameLauncher.ListGenres();
          Log($"Returning {genres.Count} genres");
          TryWrite(ctx, 200, Json(genres));
        }
        catch (Exception ex)
        {
          Log($"List genres error: {ex}");
          TryWrite(ctx, 500, Json(new { error = $"List genres failed: {ex.Message}" }));
        }
        return;
      }

      TryWrite(ctx, 404, Json(new { error = "not_found" }));
    }

    private static string Json(object o) => JsonSerializer.Serialize(o);

    private static string ReadBody(HttpListenerContext ctx)
    {
      using (var reader = new StreamReader(ctx.Request.InputStream, ctx.Request.ContentEncoding))
      {
        return reader.ReadToEnd();
      }
    }

    private static string GetLogsRoot()
    {
      var lbRoot = System.IO.Path.GetDirectoryName(System.IO.Path.GetDirectoryName(AppDomain.CurrentDomain.BaseDirectory));
      var logs = System.IO.Path.Combine(lbRoot!, "Logs", "ArcadeAssistant");
      System.IO.Directory.CreateDirectory(logs);
      return logs;
    }

    private static string GetScoresPath() => System.IO.Path.Combine(GetLogsRoot(), "scores.jsonl");
    private static string GetEventsPath() => System.IO.Path.Combine(GetLogsRoot(), "launch_events.jsonl");

    private static void AppendJsonLine(string path, object payload)
    {
      var json = Json(payload) + "\r\n";
      System.IO.File.AppendAllText(path, json, Encoding.UTF8);
    }

    private static (long bestScore, string bestPlayer, int attempts, DateTime? lastUpdated) AggregateScoresByGame(string gameId)
    {
      long best = 0; string bestPlayer = ""; int attempts = 0; DateTime? last = null;
      var p = GetScoresPath();
      if (!System.IO.File.Exists(p)) return (0, "", 0, null);
      foreach (var line in System.IO.File.ReadLines(p))
      {
        if (string.IsNullOrWhiteSpace(line)) continue;
        try
        {
          var doc = JsonDocument.Parse(line);
          var root = doc.RootElement;
          if (root.TryGetProperty("gameId", out var gid) && gid.GetString() == gameId)
          {
            attempts++;
            var s = root.TryGetProperty("score", out var sc) ? sc.GetInt64() : 0;
            var pl = root.TryGetProperty("player", out var plEl) ? plEl.GetString() : "";
            var ts = root.TryGetProperty("ts", out var tsEl) ? tsEl.GetString() : null;
            DateTime dt; if (DateTime.TryParse(ts, out dt)) { if (last==null || dt>last) last = dt; }
            if (s > best) { best = s; bestPlayer = pl ?? ""; }
          }
        }
        catch { /* ignore bad lines */ }
      }
      return (best, bestPlayer, attempts, last);
    }

    private static object AggregateLeaderboard(int limit)
    {
      var p = GetScoresPath();
      var bestByGame = new Dictionary<string, (long score, string player, string title)>();
      if (!System.IO.File.Exists(p)) return new object[0];
      foreach (var line in System.IO.File.ReadLines(p))
      {
        if (string.IsNullOrWhiteSpace(line)) continue;
        try
        {
          var doc = JsonDocument.Parse(line);
          var root = doc.RootElement;
          var gid = root.TryGetProperty("gameId", out var gidEl) ? gidEl.GetString() : null;
          if (string.IsNullOrEmpty(gid)) continue;
          var s = root.TryGetProperty("score", out var sc) ? sc.GetInt64() : 0;
          var pl = root.TryGetProperty("player", out var plEl) ? plEl.GetString() : "";
          var title = root.TryGetProperty("title", out var tEl) ? tEl.GetString() : null;
          if (!bestByGame.ContainsKey(gid) || s > bestByGame[gid].score)
          {
            bestByGame[gid] = (s, pl ?? "", title ?? "");
          }
        }
        catch { /* ignore bad lines */ }
      }

      var list = new List<Dictionary<string, object?>>();
      foreach (var kv in bestByGame)
      {
        var item = new Dictionary<string, object?>
        {
          ["gameId"] = kv.Key,
          ["title"] = kv.Value.title,
          ["bestScore"] = kv.Value.score,
          ["bestPlayer"] = kv.Value.player
        };
        list.Add(item);
      }
      list.Sort((a,b) => ((long)b["bestScore"]).CompareTo((long)a["bestScore"]));
      if (limit > 0 && list.Count > limit) list = list.GetRange(0, limit);
      return list;
    }

    // Rate limiting for launch requests (prevent rapid-fire launches)
    private static readonly System.Collections.Generic.Dictionary<string, DateTime> _lastLaunchTime = new System.Collections.Generic.Dictionary<string, DateTime>();
    private static readonly object _launchLock = new object();
    private static readonly TimeSpan _launchThrottle = TimeSpan.FromSeconds(2);

    private static bool IsLaunchThrottled(string gameId)
    {
      lock (_launchLock)
      {
        if (_lastLaunchTime.TryGetValue(gameId, out var lastTime))
        {
          var elapsed = DateTime.UtcNow - lastTime;
          if (elapsed < _launchThrottle)
          {
            Log($"Launch throttled for {gameId}: {elapsed.TotalSeconds:F1}s < {_launchThrottle.TotalSeconds}s");
            return true;
          }
        }
        _lastLaunchTime[gameId] = DateTime.UtcNow;
        return false;
      }
    }

    // -------------------- Helpers: Import --------------------
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

    private static object ListMissingInternal(string platform, string folder, string[] exts)
    {
      var existing = new System.Collections.Generic.HashSet<string>(StringComparer.OrdinalIgnoreCase);
      try
      {
        var all = Unbroken.LaunchBox.Plugins.PluginHelper.DataManager.GetAllGames();
        foreach (var g in all)
        {
          if (g == null) continue;
          var gp = g.Platform ?? string.Empty;
          if (!string.Equals(gp, platform, StringComparison.OrdinalIgnoreCase)) continue;
          var ap = g.ApplicationPath ?? string.Empty;
          if (!string.IsNullOrWhiteSpace(ap)) existing.Add(System.IO.Path.GetFullPath(ap));
        }
      } catch (Exception ex) { Log("Existing scan error: " + ex.Message); }

      var files = new System.Collections.Generic.List<object>();
      int existingCount = 0;
      try
      {
        foreach (var path in Directory.EnumerateFiles(folder))
        {
          var ext = System.IO.Path.GetExtension(path)?.ToLowerInvariant() ?? string.Empty;
          if (!exts.Contains(ext)) continue;
          var full = System.IO.Path.GetFullPath(path);
          if (existing.Contains(full)) { existingCount++; continue; }
          var name = System.IO.Path.GetFileNameWithoutExtension(path);
          files.Add(new { path = full, name });
        }
      } catch (Exception ex) { Log("Folder scan error: " + ex.Message); }

      return new { platform, folder, missing = files, counts = new { missing = files.Count, existing = existingCount } };
    }

    private static (int added, int skipped, int duplicates, System.Collections.Generic.List<object> errors) ImportMissingInternal(string platform, object scanResult)
    {
      int added = 0, skipped = 0, duplicates = 0;
      var errors = new System.Collections.Generic.List<object>();

      var scanType = scanResult.GetType();
      var missingProp = scanType.GetProperty("missing");
      var missingList = missingProp?.GetValue(scanResult) as System.Collections.IEnumerable;
      if (missingList == null) return (0, 0, 0, errors);

      foreach (var item in missingList)
      {
        try
        {
          var it = item.GetType();
          var path = it.GetProperty("path")?.GetValue(item) as string ?? string.Empty;
          var name = it.GetProperty("name")?.GetValue(item) as string ?? System.IO.Path.GetFileNameWithoutExtension(path);
          if (string.IsNullOrWhiteSpace(path)) { skipped++; continue; }

          if (TryAddGame(platform, name, path)) { added++; }
          else { skipped++; }
        }
        catch (Exception ex)
        {
          try
          {
            var it2 = item.GetType();
            var path2 = it2.GetProperty("path")?.GetValue(item) as string ?? string.Empty;
            errors.Add(new { path = path2, error = ex.Message });
          }
          catch { errors.Add(new { error = ex.Message }); }
        }
      }

      return (added, skipped, duplicates, errors);
    }

    private static bool TryAddGame(string platform, string title, string applicationPath)
    {
      try
      {
        // Normalize title from filename if needed
        if (string.IsNullOrWhiteSpace(title))
        {
          title = System.IO.Path.GetFileNameWithoutExtension(applicationPath) ?? string.Empty;
        }
        title = title.Replace('_', ' ').Replace('.', ' ').Trim();

        var dm = Unbroken.LaunchBox.Plugins.PluginHelper.DataManager;
        if (dm == null) return false;

        var dmType = dm.GetType();

        var method = dmType.GetMethod("AddNewGame", new Type[] { typeof(string), typeof(string), typeof(string) });
        if (method != null)
        {
          var res = method.Invoke(dm, new object[] { title, applicationPath, platform });
          return res != null;
        }

        var all = Unbroken.LaunchBox.Plugins.PluginHelper.DataManager.GetAllGames();
        var exemplar = all.FirstOrDefault();
        var gameType = exemplar?.GetType();
        if (gameType != null)
        {
          var newGame = Activator.CreateInstance(gameType);
          var pTitle = gameType.GetProperty("Title"); pTitle?.SetValue(newGame, title);
          var pPlatform = gameType.GetProperty("Platform"); pPlatform?.SetValue(newGame, platform);
          var pPath = gameType.GetProperty("ApplicationPath"); pPath?.SetValue(newGame, applicationPath);

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
        Log("Add game error: " + ex.Message);
      }
      return false;
    }

    private static void TryWrite(HttpListenerContext ctx, int code, string body)
    {
      try
      {
        ctx.Response.StatusCode = code;
        ctx.Response.ContentType = "application/json";
        var bytes = Encoding.UTF8.GetBytes(body);
        ctx.Response.ContentLength64 = bytes.Length;
        ctx.Response.OutputStream.Write(bytes, 0, bytes.Length);
      }
      catch (Exception ex)
      {
        Log("Write error: " + ex);
      }
      finally
      {
        try { ctx.Response.OutputStream.Close(); } catch { }
        try { ctx.Response.Close(); } catch { }
      }
    }

    private static void Log(string msg)
    {
      try
      {
        // Use portable path - works on any drive where LaunchBox is installed
        var lbRoot = System.IO.Path.GetDirectoryName(System.IO.Path.GetDirectoryName(AppDomain.CurrentDomain.BaseDirectory));
        var p = System.IO.Path.Combine(lbRoot!, "Logs", "ArcadeAssistant.log");
        System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(p)!);
        System.IO.File.AppendAllText(p, $"[{DateTime.Now:u}] {msg}\r\n");
      } catch { /* never crash host */ }
    }

    private static bool TryStartListener(int port)
    {
      try
      {
        _listener!.Prefixes.Clear();
        // Bind explicitly to 127.0.0.1 to avoid IPv6 and ACL issues
        _listener!.Prefixes.Add($"http://127.0.0.1:{port}/");
        _listener!.Start();
        return true;
      }
      catch (Exception ex)
      {
        Log($"Failed to bind to port {port}: {ex.Message}");
        Log($"If this is an ACL issue, run (elevated): netsh http add urlacl url=http://127.0.0.1:{port}/ user=Everyone");
        try { _listener!.Close(); } catch { }
        try { _listener = new HttpListener(); } catch { }
        return false;
      }
    }

    /// <summary>
    /// B2 FIX: Outbound notification to Python backend when a game starts.
    /// Fire-and-forget — if backend is offline, fail silently to prevent LaunchBox crash.
    /// </summary>
    private static async Task NotifyBackendGameStart(string gameId, string platform, string title)
    {
      try
      {
        var payload = new
        {
          game_id = gameId,
          platform = platform,
          title = title,
          source = "launchbox_bridge",
          timestamp = (int)(DateTime.UtcNow.Subtract(new DateTime(1970, 1, 1))).TotalSeconds
        };

        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");

        // POST to the Python Hands API Router
        await _httpClient.PostAsync("http://localhost:8000/api/game/start", content);
        Log($"Backend notified of game start: {title}");
      }
      catch (Exception ex)
      {
        // Backend offline — fail silently to prevent LaunchBox crash
        Log($"Backend notification failed (non-critical): {ex.Message}");
      }
    }
  }
}
