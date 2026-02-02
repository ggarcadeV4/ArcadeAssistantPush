namespace ArcadeAssistantPlugin.Models
{
    /// <summary>
    /// Game metadata returned from search results
    /// </summary>
    public class GameInfo
    {
        public string Id { get; set; }
        public string Title { get; set; }
        public string Platform { get; set; }
        public string Developer { get; set; }
        public string Publisher { get; set; }
        public string Genre { get; set; }
        public string ReleaseDate { get; set; }
        public string ApplicationPath { get; set; }
    }
}
