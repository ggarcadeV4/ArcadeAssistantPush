using System.Text.Json.Serialization;

namespace ArcadeAssistant.Plugin.Models
{
    /// <summary>
    /// Request body for launching a game
    /// Supports both "GameId" and "id" field names for backwards compatibility
    /// </summary>
    public class LaunchRequest
    {
        public string GameId { get; set; }

        [JsonPropertyName("id")]
        public string Id { get; set; }

        /// <summary>
        /// Gets the game ID from either field name
        /// </summary>
        public string GetGameId()
        {
            return !string.IsNullOrEmpty(GameId) ? GameId : Id;
        }
    }
}
