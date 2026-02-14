namespace ArcadeAssistantPlugin.Models
{
    /// <summary>
    /// Request body for searching games (currently using query string, but here for future use)
    /// </summary>
    public class SearchRequest
    {
        public string Title { get; set; }
    }
}
