using System.Collections;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace GameAssetRag.Tests
{
    /// <summary>
    /// README 용 데모 촬영. 로컬 서버(python src/server.py)가 떠 있어야 한다.
    ///   Unity -batchmode -projectPath unity -runTests -testPlatform PlayMode -testFilter GameAssetRag.Tests.NpcDemoCapture
    /// (-nographics 없이). 프레임은 unity/artifacts/frames/npc/ 에 PNG 로 떨어진다.
    /// 게임 시간을 프레임에 고정하므로(captureFramerate) PNG 저장이 느려도 영상 속도는 실제 속도와 같다.
    /// 답은 촬영 전에 한 번 물어 서버 캐시에 올려 두고, 화면의 대기 구간은 minWaitSeconds 로 고정한다 —
    /// 실측 지연은 화면 아래 상태줄과 results/answer_eval.md 에 있다.
    /// </summary>
    public class NpcDemoCapture
    {
        private const int Width = 1280, Height = 720, Fps = 15;

        private static readonly string[] Questions =
        {
            "불에 잘 버티는 방패 추천해줘",   // 속성 질문
            "뱀이 감겨 있는 지팡이",         // 시각 질문 — 아이콘 라벨이 없으면 못 찾는다
            "하늘을 날게 해주는 물약",       // 데이터에 답이 없는 질문
        };

        private bool _recording;

        [UnityTest, Explicit, Category("Capture")]
        public IEnumerator Capture()
        {
            var camera = new GameObject("Main Camera").AddComponent<Camera>();
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = Color.black;
            camera.orthographic = true;
            // UI 를 만들기 전에 렌더 텍스처를 붙인다 — 나중에 붙이면 캔버스 배율이 바뀌면서 먼저 그려진 글자가 흐리게 남는다
            var target = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32) { antiAliasing = 4 };
            camera.targetTexture = target;

            var go = new GameObject("NpcDialog");
            go.SetActive(false);                       // Awake 전에 카메라를 넘기려고
            var client = go.AddComponent<NpcClient>();
            var ui = go.AddComponent<NpcDialogUI>();
            ui.uiCamera = camera;
            ui.minWaitSeconds = 1.4f;
            go.SetActive(true);
            yield return null;

            // 촬영 전: 답을 서버 캐시에 올린다(실패하면 서버가 안 떠 있는 것)
            foreach (string q in Questions)
            {
                string error = null;
                yield return client.Ask(q, _ => { }, e => error = e);
                Assert.IsNull(error, error);
            }

            int previous = Time.captureFramerate;
            Time.captureFramerate = Fps;
            _recording = true;
            ui.StartCoroutine(Record(camera, target, "npc"));

            yield return new WaitForSeconds(1.5f);
            foreach (string q in Questions)
            {
                for (int n = 1; n <= q.Length; n++)
                {
                    ui.InputText = q.Substring(0, n);
                    yield return new WaitForSeconds(0.07f);
                }

                yield return new WaitForSeconds(0.4f);
                ui.Submit();
                while (ui.Busy)
                    yield return null;
                yield return new WaitForSeconds(3.0f);
            }

            _recording = false;
            yield return null;
            Time.captureFramerate = previous;
            Object.Destroy(go);
            camera.targetTexture = null;
            Object.Destroy(camera.gameObject);
            Object.Destroy(target);
        }

        private IEnumerator Record(Camera camera, RenderTexture target, string name)
        {
            string dir = Path.Combine(Directory.GetParent(Application.dataPath).FullName, "artifacts", "frames", name);
            if (Directory.Exists(dir))
                Directory.Delete(dir, true);
            Directory.CreateDirectory(dir);

            var pixels = new Texture2D(Width, Height, TextureFormat.RGB24, false);
            for (int frame = 0; _recording; frame++)
            {
                yield return null;
                camera.Render();
                RenderTexture active = RenderTexture.active;
                RenderTexture.active = target;
                pixels.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                pixels.Apply(false);
                RenderTexture.active = active;
                File.WriteAllBytes(Path.Combine(dir, $"{frame:D4}.png"), pixels.EncodeToPNG());
            }

            Object.Destroy(pixels);
        }
    }
}
