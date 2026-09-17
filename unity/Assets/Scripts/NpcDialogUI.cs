using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace GameAssetRag
{
    /// <summary>
    /// NPC 대화 화면. 질문 → 서버 → 답을 한 글자씩 보여 주고, 답의 근거가 된 아이템·퀘스트를 카드로 띄운다.
    /// 화면은 실행 시 코드로 만든다(씬 파일에는 이 컴포넌트와 카메라만 있다). 기준 해상도 1280×720.
    /// </summary>
    [RequireComponent(typeof(NpcClient))]
    public class NpcDialogUI : MonoBehaviour
    {
        public Camera uiCamera;
        public float charsPerSecond = 45f;

        /// <summary>답이 캐시에서 바로 와도 "기록을 찾는 중"을 이만큼은 보여 준다(촬영용, 평소 0).</summary>
        public float minWaitSeconds;

        public bool Busy { get; private set; }
        public string InputText
        {
            get => _input.text;
            set => _input.text = value;
        }

        private static readonly Color Bg0 = Hex("0b0e17"), Bg1 = Hex("182038"), PanelColor = Hex("1b2236"), CardColor = Hex("242e49");
        private static readonly Color Gold = Hex("d9b86a"), TextMain = Hex("f0ede4"), TextMuted = Hex("8e99b8"), Player = Hex("aab4cf");
        private static readonly Color Ok = Hex("6fcf97"), Unknown = Hex("e0a458"), Error = Hex("e07a7a");

        private const string Greeting = "어서 오세요, 실버브룩 기록 보관소입니다. 아이템이나 의뢰에 대해 물어보세요. 기록에 없는 것은 없다고 말씀드립니다.";

        private NpcClient _client;
        private Font _font;
        private Sprite _rounded;
        private RectTransform _root, _cards;
        private Text _who, _question, _answer, _badge, _status, _cardsTitle;
        private Image _badgeBg;
        private InputField _input;
        private Button _send;
        private readonly List<Texture2D> _iconTextures = new List<Texture2D>();

        private void Awake()
        {
            _client = GetComponent<NpcClient>();
            _font = Font.CreateDynamicFontFromOSFont(new[] { "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR" }, 24);
            _rounded = MakeRoundedSprite(64, 18);
            Build();
            _answer.text = Greeting;
        }

        private void OnDestroy() => ClearCards();

        public void Submit()
        {
            string query = _input.text.Trim();
            if (Busy || query.Length == 0)
                return;
            StartCoroutine(AskRoutine(query));
        }

        private IEnumerator AskRoutine(string query)
        {
            Busy = true;
            _send.interactable = false;
            _input.text = "";
            _who.text = "플레이어";
            _question.text = query;
            ClearCards();
            SetBadge("", Color.clear);
            _status.text = "";

            AskResponse res = null;
            string error = null;
            Coroutine dots = StartCoroutine(WaitingDots());
            float asked = Time.time;
            yield return _client.Ask(query, r => res = r, e => error = e);
            while (Time.time - asked < minWaitSeconds)
                yield return null;
            StopCoroutine(dots);

            if (error != null)
            {
                SetBadge("연결 실패", Error);
                _answer.text = error;
            }
            else
            {
                SetBadge(res.answerable ? "기록에 있음" : "기록에 없음", res.answerable ? Ok : Unknown);
                yield return TypeRoutine(res.answer);
                yield return ShowCards(res.citations);
                _status.text = $"검색 {res.search_s:0.00}초 · 생성 {res.latency_s:0.0}초 · ${res.cost_usd:0.0000} · {res.model}" + (res.cached ? " · 캐시된 답" : "");
            }

            _send.interactable = true;
            Busy = false;
            _input.ActivateInputField();
        }

        private IEnumerator WaitingDots()
        {
            for (int i = 0; ; i++)
            {
                _answer.text = "기록을 찾는 중" + new string('.', i % 4);
                yield return new WaitForSeconds(0.3f);
            }
        }

        private IEnumerator TypeRoutine(string text)
        {
            float shown = 0f;
            while (shown < text.Length)
            {
                shown += charsPerSecond * Time.deltaTime;
                _answer.text = text.Substring(0, Mathf.Min(text.Length, Mathf.FloorToInt(shown)));
                yield return null;
            }

            _answer.text = text;
        }

        private IEnumerator ShowCards(Citation[] citations)
        {
            _cardsTitle.text = citations != null && citations.Length > 0 ? "근거가 된 기록" : "";
            if (citations == null)
                yield break;

            for (int i = 0; i < citations.Length && i < 5; i++)
            {
                Citation c = citations[i];
                RectTransform card = Panel(_cards, "Card", CardColor);
                Place(card, new Vector2(0, 1), new Vector2(0, 1), new Vector2(i * 172f, 0), new Vector2(160, 172));

                if (!string.IsNullOrEmpty(c.icon))
                {
                    var icon = new GameObject("Icon", typeof(RawImage)).GetComponent<RawImage>();
                    icon.transform.SetParent(card, false);
                    icon.color = Color.clear;
                    Place(icon.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -12), new Vector2(92, 92));
                    StartCoroutine(_client.LoadIcon(c.icon, tex =>
                    {
                        _iconTextures.Add(tex);
                        icon.texture = tex;
                        icon.color = TextMain;
                    }));
                }
                else
                {
                    Text glyph = Label(card, "의뢰", 30, Gold, TextAnchor.MiddleCenter);
                    Place(glyph.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -12), new Vector2(140, 92));
                }

                Text name = Label(card, c.name, 15, TextMain, TextAnchor.UpperCenter);
                Place(name.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -110), new Vector2(148, 40));
                Text id = Label(card, c.id, 11, TextMuted, TextAnchor.LowerCenter);
                Place(id.rectTransform, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 8), new Vector2(148, 16));

                yield return new WaitForSeconds(0.12f);
            }
        }

        private void ClearCards()
        {
            if (_cards != null)
                foreach (Transform child in _cards)
                    Destroy(child.gameObject);
            foreach (Texture2D tex in _iconTextures)
                Destroy(tex);
            _iconTextures.Clear();
            if (_cardsTitle != null)
                _cardsTitle.text = "";
        }

        private void SetBadge(string text, Color color)
        {
            _badge.text = text;
            _badgeBg.color = text.Length == 0 ? Color.clear : new Color(color.r, color.g, color.b, 0.18f);
            _badge.color = color;
        }

        // ---------- 화면 구성 ----------
        private void Build()
        {
            if (FindFirstObjectByType<EventSystem>() == null)
                new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));

            var canvasGo = new GameObject("Canvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            var canvas = canvasGo.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceCamera;
            canvas.worldCamera = uiCamera != null ? uiCamera : Camera.main;
            canvas.planeDistance = 1f;
            var scaler = canvasGo.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1280, 720);
            scaler.matchWidthOrHeight = 0.5f;
            _root = canvasGo.GetComponent<RectTransform>();

            var bg = new GameObject("Background", typeof(RawImage)).GetComponent<RawImage>();
            bg.transform.SetParent(_root, false);
            bg.texture = MakeGradient(Bg0, Bg1);
            bg.raycastTarget = false;
            Stretch(bg.rectTransform);

            Text title = Label(_root, "에버셰이드 연대기", 20, Gold, TextAnchor.MiddleLeft);
            Place(title.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(40, -22), new Vector2(400, 30));
            Text tag = Label(_root, "검색 기반 NPC · 기록에 있는 것만 답합니다", 14, TextMuted, TextAnchor.MiddleRight);
            Place(tag.rectTransform, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-40, -22), new Vector2(500, 30));

            // 왼쪽: NPC
            RectTransform frame = Panel(_root, "PortraitFrame", new Color(Gold.r, Gold.g, Gold.b, 0.55f));
            Place(frame, new Vector2(0, 1), new Vector2(0, 1), new Vector2(40, -72), new Vector2(280, 380));
            RectTransform portraitPanel = Panel(frame, "PortraitPanel", PanelColor);
            Stretch(portraitPanel, 2);

            var portrait = new GameObject("Portrait", typeof(RawImage)).GetComponent<RawImage>();
            portrait.transform.SetParent(portraitPanel, false);
            portrait.raycastTarget = false;
            var bytes = Resources.Load<TextAsset>("npc_portrait");
            if (bytes != null)
            {
                var raw = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                raw.LoadImage(bytes.bytes);
                portrait.texture = IconUtil.ToWhiteSilhouette(raw);
                portrait.color = new Color(TextMain.r, TextMain.g, TextMain.b, 0.92f);
            }

            Place(portrait.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -28), new Vector2(210, 210));
            Text npcName = Label(portraitPanel, "안내원 세라", 26, TextMain, TextAnchor.MiddleCenter);
            Place(npcName.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -262), new Vector2(260, 36));
            Text npcSub = Label(portraitPanel, "실버브룩 기록 보관소", 15, Gold, TextAnchor.MiddleCenter);
            Place(npcSub.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -300), new Vector2(260, 24));
            Text npcNote = Label(portraitPanel, "아이템 150 · 의뢰 40", 13, TextMuted, TextAnchor.MiddleCenter);
            Place(npcNote.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -330), new Vector2(260, 22));

            // 오른쪽: 질문·답·근거
            _who = Label(_root, "", 13, TextMuted, TextAnchor.MiddleLeft);
            Place(_who.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(352, -72), new Vector2(100, 20));
            _question = Label(_root, "", 22, Player, TextAnchor.MiddleLeft);
            Place(_question.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(352, -92), new Vector2(880, 34));

            RectTransform answerPanel = Panel(_root, "AnswerPanel", PanelColor);
            Place(answerPanel, new Vector2(0, 1), new Vector2(0, 1), new Vector2(350, -136), new Vector2(890, 236));
            RectTransform badge = Panel(answerPanel, "Badge", Color.clear);
            Place(badge, new Vector2(0, 1), new Vector2(0, 1), new Vector2(22, -16), new Vector2(118, 28));
            _badgeBg = badge.GetComponent<Image>();
            _badge = Label(badge, "", 14, Ok, TextAnchor.MiddleCenter);
            Stretch(_badge.rectTransform);
            _answer = Label(answerPanel, "", 21, TextMain, TextAnchor.UpperLeft);
            _answer.lineSpacing = 1.3f;
            _answer.rectTransform.anchorMin = Vector2.zero;
            _answer.rectTransform.anchorMax = Vector2.one;
            _answer.rectTransform.offsetMin = new Vector2(24, 16);
            _answer.rectTransform.offsetMax = new Vector2(-24, -54);

            _cardsTitle = Label(_root, "", 14, TextMuted, TextAnchor.MiddleLeft);
            Place(_cardsTitle.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(352, -384), new Vector2(300, 22));
            _cards = new GameObject("Cards", typeof(RectTransform)).GetComponent<RectTransform>();
            _cards.SetParent(_root, false);
            Place(_cards, new Vector2(0, 1), new Vector2(0, 1), new Vector2(350, -410), new Vector2(890, 172));

            _status = Label(_root, "", 13, TextMuted, TextAnchor.MiddleRight);
            Place(_status.rectTransform, new Vector2(1, 0), new Vector2(1, 0), new Vector2(-40, 96), new Vector2(880, 20));

            // 아래: 입력
            RectTransform inputPanel = Panel(_root, "Input", CardColor);
            Place(inputPanel, new Vector2(0, 0), new Vector2(0, 0), new Vector2(40, 32), new Vector2(1070, 54));
            _input = inputPanel.gameObject.AddComponent<InputField>();
            Text inputText = Label(inputPanel, "", 20, TextMain, TextAnchor.MiddleLeft);
            inputText.supportRichText = false;
            Stretch(inputText.rectTransform, 20, 6);
            Text placeholder = Label(inputPanel, "무엇이든 물어보세요 — 예: 불에 잘 버티는 방패 추천해줘", 20, TextMuted, TextAnchor.MiddleLeft);
            Stretch(placeholder.rectTransform, 20, 6);
            _input.textComponent = inputText;
            _input.placeholder = placeholder;
            _input.characterLimit = 200;
            _input.lineType = InputField.LineType.SingleLine;
            _input.onSubmit.AddListener(_ => Submit());

            RectTransform sendPanel = Panel(_root, "Send", Gold);
            Place(sendPanel, new Vector2(1, 0), new Vector2(1, 0), new Vector2(-40, 32), new Vector2(118, 54));
            _send = sendPanel.gameObject.AddComponent<Button>();
            _send.onClick.AddListener(Submit);
            Text sendLabel = Label(sendPanel, "묻기", 20, Bg0, TextAnchor.MiddleCenter);
            Stretch(sendLabel.rectTransform);
        }

        private RectTransform Panel(Transform parent, string name, Color color)
        {
            var image = new GameObject(name, typeof(Image)).GetComponent<Image>();
            image.transform.SetParent(parent, false);
            image.sprite = _rounded;
            image.type = Image.Type.Sliced;
            image.color = color;
            return image.rectTransform;
        }

        private Text Label(Transform parent, string text, int size, Color color, TextAnchor anchor)
        {
            var label = new GameObject("Text", typeof(Text)).GetComponent<Text>();
            label.transform.SetParent(parent, false);
            label.font = _font;
            label.fontSize = size;
            label.color = color;
            label.alignment = anchor;
            label.text = text;
            label.horizontalOverflow = HorizontalWrapMode.Wrap;
            label.verticalOverflow = VerticalWrapMode.Truncate;
            label.raycastTarget = false;
            return label;
        }

        /// <summary>anchor 와 pivot 을 같은 모서리에 두고, 그 모서리 기준 위치와 크기를 준다.</summary>
        private static void Place(RectTransform rt, Vector2 anchor, Vector2 pivot, Vector2 position, Vector2 size)
        {
            rt.anchorMin = rt.anchorMax = anchor;
            rt.pivot = pivot;
            rt.anchoredPosition = position;
            rt.sizeDelta = size;
        }

        private static void Stretch(RectTransform rt, float padX = 0, float padY = -1)
        {
            if (padY < 0)
                padY = padX;
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = new Vector2(padX, padY);
            rt.offsetMax = new Vector2(-padX, -padY);
        }

        private static Texture2D MakeGradient(Color bottom, Color top)
        {
            var tex = new Texture2D(1, 256, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
            for (int y = 0; y < 256; y++)
                tex.SetPixel(0, y, Color.Lerp(bottom, top, y / 255f));
            tex.Apply();
            return tex;
        }

        private static Sprite MakeRoundedSprite(int size, int radius)
        {
            var tex = new Texture2D(size, size, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float cx = Mathf.Clamp(x + 0.5f, radius, size - radius);
                    float cy = Mathf.Clamp(y + 0.5f, radius, size - radius);
                    float d = Vector2.Distance(new Vector2(x + 0.5f, y + 0.5f), new Vector2(cx, cy));
                    tex.SetPixel(x, y, new Color(1, 1, 1, Mathf.Clamp01(radius - d + 0.5f)));
                }
            }

            tex.Apply();
            return Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0,
                SpriteMeshType.FullRect, new Vector4(radius, radius, radius, radius));
        }

        private static Color Hex(string hex)
        {
            ColorUtility.TryParseHtmlString("#" + hex, out Color c);
            return c;
        }
    }
}
