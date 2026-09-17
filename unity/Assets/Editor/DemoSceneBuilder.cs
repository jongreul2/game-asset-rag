using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace GameAssetRag.Editor
{
    /// <summary>
    /// NpcDemo 씬을 코드로 만든다: -quit -executeMethod GameAssetRag.Editor.DemoSceneBuilder.BuildAll
    /// </summary>
    public static class DemoSceneBuilder
    {
        public const string ScenePath = "Assets/Scenes/NpcDemo.unity";

        [MenuItem("GameAssetRag/Build Demo Scene")]
        public static void BuildAll()
        {
            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var camera = new GameObject("Main Camera").AddComponent<Camera>();
            camera.tag = "MainCamera";
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0.043f, 0.055f, 0.09f);
            camera.orthographic = true;

            var npc = new GameObject("NpcDialog");
            npc.AddComponent<NpcClient>();
            npc.AddComponent<NpcDialogUI>().uiCamera = camera;

            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            Debug.Log("[DemoSceneBuilder] saved " + ScenePath);
        }
    }
}
