using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace GameAssetRag
{
    [Serializable]
    public class Citation
    {
        public string id;
        public string kind;   // "item" | "quest"
        public string name;
        public string icon;   // 퀘스트는 비어 있다
    }

    [Serializable]
    public class AskResponse
    {
        public bool answerable;
        public string answer;
        public Citation[] citations;
        public string model;
        public float search_s;
        public float latency_s;
        public float cost_usd;
        public bool cached;
    }

    /// <summary>
    /// 로컬 NPC 서버(src/server.py)와 통신한다. 클라이언트는 질문을 보내고 답·근거 id·아이콘만 받는다.
    /// LLM·임베딩 API 키는 서버에만 있고 이 코드에는 없다 — 클라이언트는 사용자 기기에서 실행되기 때문이다.
    /// </summary>
    public class NpcClient : MonoBehaviour
    {
        public string baseUrl = "http://127.0.0.1:8765";
        public int timeoutSeconds = 180;

        [Serializable]
        private class AskRequest
        {
            public string query;
        }

        public IEnumerator Ask(string query, Action<AskResponse> onOk, Action<string> onError)
        {
            byte[] body = Encoding.UTF8.GetBytes(JsonUtility.ToJson(new AskRequest { query = query }));
            using (var req = new UnityWebRequest(baseUrl + "/ask", UnityWebRequest.kHttpVerbPOST))
            {
                req.uploadHandler = new UploadHandlerRaw(body);
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");
                req.timeout = timeoutSeconds;
                yield return req.SendWebRequest();

                if (req.result != UnityWebRequest.Result.Success)
                {
                    onError(req.responseCode == 0 ? "서버에 연결할 수 없습니다 (python src/server.py)" : $"서버 오류 {req.responseCode}");
                    yield break;
                }

                AskResponse res = null;
                try
                {
                    res = JsonUtility.FromJson<AskResponse>(req.downloadHandler.text);
                }
                catch (ArgumentException)
                {
                    // 아래에서 null 로 처리
                }

                if (res == null || string.IsNullOrEmpty(res.answer))
                    onError("답을 해석하지 못했습니다");
                else
                    onOk(res);
            }
        }

        public IEnumerator LoadIcon(string file, Action<Texture2D> onOk)
        {
            using (var req = UnityWebRequest.Get(baseUrl + "/icons/" + UnityWebRequest.EscapeURL(file)))
            {
                req.timeout = 15;
                yield return req.SendWebRequest();
                if (req.result != UnityWebRequest.Result.Success)
                    yield break;

                var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (tex.LoadImage(req.downloadHandler.data))
                    onOk(IconUtil.ToWhiteSilhouette(tex));
            }
        }
    }

    public static class IconUtil
    {
        /// <summary>검은 그림 / 흰 배경 아이콘을 흰 그림 / 투명 배경으로 바꾼다(어두운 UI 위에 색을 입혀 쓰려고).</summary>
        public static Texture2D ToWhiteSilhouette(Texture2D source)
        {
            Color32[] px = source.GetPixels32();
            for (int i = 0; i < px.Length; i++)
            {
                int lum = (px[i].r * 77 + px[i].g * 150 + px[i].b * 29) >> 8;
                px[i] = new Color32(255, 255, 255, (byte)(255 - lum));
            }

            var result = new Texture2D(source.width, source.height, TextureFormat.RGBA32, true);
            result.SetPixels32(px);
            result.Apply(true);
            result.filterMode = FilterMode.Trilinear;
            UnityEngine.Object.Destroy(source);
            return result;
        }
    }
}
