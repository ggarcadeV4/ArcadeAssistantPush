using System;
    using System.Collections.Generic;
    using System.Collections;
    using System.Linq;
    using Unbroken.LaunchBox.Plugins;
    using Unbroken.LaunchBox.Plugins.Data;
    using ArcadeAssistantPlugin.Models;

namespace ArcadeAssistantPlugin
{
    /// <summary>
    /// Wrapper around LaunchBox Plugin API for game operations
    /// </summary>
        public static class GameLauncher
        {
            private const int MAX_SEARCH_RESULTS = 50;

            private static string GetGenreSafe(IGame game)
            {
                try
                {
                    if (game == null) return string.Empty;

                    var type = game.GetType();
                    var genreProp = type.GetProperty("Genre");
                    if (genreProp != null)
                    {
                        var val = genreProp.GetValue(game) as string;
                        return val ?? string.Empty;
                    }

                    var genresProp = type.GetProperty("Genres");
                    if (genresProp != null)
                    {
                        var genresVal = genresProp.GetValue(game) as IEnumerable;
                        if (genresVal != null)
                        {
                            var names = new List<string>();
                            foreach (var item in genresVal)
                            {
                                if (item == null) continue;
                                var itemType = item.GetType();
                                var nameProp = itemType.GetProperty("Name");
                                if (nameProp != null)
                                {
                                    var name = nameProp.GetValue(item) as string;
                                    if (!string.IsNullOrWhiteSpace(name)) names.Add(name);
                                }
                                else
                                {
                                    names.Add(item.ToString());
                                }
                            }
                            return string.Join(", ", names.Where(s => !string.IsNullOrWhiteSpace(s)));
                        }
                    }

                    return string.Empty;
                }
                catch
                {
                    return string.Empty;
                }
            }

        /// <summary>
        /// Search for games by title (case-insensitive partial match)
        /// </summary>
        public static List<GameInfo> SearchGames(string query)
        {
            try
            {
                var allGames = PluginHelper.DataManager.GetAllGames();

                if (allGames == null)
                {
                    Console.WriteLine("[GameLauncher] DataManager returned null");
                    return new List<GameInfo>();
                }

                var matches = allGames
                    .Where(g => g != null && g.Title != null &&
                               g.Title.IndexOf(query, StringComparison.OrdinalIgnoreCase) >= 0)
                    .OrderBy(g => g.Title)
                    .Take(MAX_SEARCH_RESULTS)
                        .Select(g => new GameInfo
                        {
                            Id = g.Id,
                            Title = g.Title,
                            Platform = g.Platform ?? "Unknown",
                            Developer = g.Developer ?? "",
                            Publisher = g.Publisher ?? "",
                            Genre = GetGenreSafe(g),
                            ReleaseDate = g.ReleaseDate?.Year.ToString() ?? "",
                            ApplicationPath = g.ApplicationPath ?? ""
                        })
                        .ToList();

                    Console.WriteLine($"[GameLauncher] Found {matches.Count()} games matching '{query}'");
                    return matches;
                }
            catch (Exception ex)
            {
                Console.WriteLine($"[GameLauncher] Search error: {ex.Message}");
                return new List<GameInfo>();
            }
        }

        /// <summary>
        /// Launch a game by its LaunchBox ID
        /// </summary>
        public static bool LaunchGame(string gameId)
        {
            try
            {
                var game = PluginHelper.DataManager.GetGameById(gameId);

                if (game == null)
                {
                    Console.WriteLine($"[GameLauncher] Game not found: {gameId}");
                    return false;
                }

                Console.WriteLine($"[GameLauncher] Launching: {game.Title} ({game.Platform})");

                    PluginHelper.LaunchBoxMainViewModel.PlayGame(game, null, null, string.Empty);

                    return true;
                }
            catch (Exception ex)
            {
                Console.WriteLine($"[GameLauncher] Launch error: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// Get all unique platforms in the library
        /// </summary>
        public static List<string> ListPlatforms()
        {
            try
            {
                var allGames = PluginHelper.DataManager.GetAllGames();

                if (allGames == null)
                {
                    Console.WriteLine("[GameLauncher] DataManager returned null");
                    return new List<string>();
                }

                    var platforms = allGames
                        .Select(g => g.Platform)
                        .Where(p => !string.IsNullOrEmpty(p))
                        .Distinct()
                        .OrderBy(p => p)
                        .ToList();

                    Console.WriteLine($"[GameLauncher] Found {platforms.Count()} platforms");
                    return platforms;
                }
            catch (Exception ex)
            {
                Console.WriteLine($"[GameLauncher] Platform list error: {ex.Message}");
                return new List<string>();
            }
        }

        /// <summary>
        /// Get all unique genres in the library
        /// </summary>
        public static List<string> ListGenres()
        {
            try
            {
                var allGames = PluginHelper.DataManager.GetAllGames();

                if (allGames == null)
                {
                    Console.WriteLine("[GameLauncher] DataManager returned null");
                    return new List<string>();
                }

                    var genres = allGames
                        .Select(g => GetGenreSafe(g))
                        .Where(s => !string.IsNullOrWhiteSpace(s))
                        .SelectMany(s => s.Split(new[]{","}, StringSplitOptions.RemoveEmptyEntries))
                        .Select(s => s.Trim())
                        .Where(s => s.Length > 0)
                        .Distinct(StringComparer.OrdinalIgnoreCase)
                        .OrderBy(g => g)
                        .ToList();

                    Console.WriteLine($"[GameLauncher] Found {genres.Count()} genres");
                    return genres;
                }
            catch (Exception ex)
            {
                Console.WriteLine($"[GameLauncher] Genre list error: {ex.Message}");
                return new List<string>();
            }
        }
    }
}
