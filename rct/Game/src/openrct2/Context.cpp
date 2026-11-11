/*****************************************************************************
 * Copyright (c) 2014-2025 OpenRCT2 developers
 *
 * For a complete list of all authors, please refer to contributors.md
 * Interested in contributing? Visit https://github.com/OpenRCT2/OpenRCT2
 *
 * OpenRCT2 is licensed under the GNU General Public License version 3.
 *****************************************************************************/

//#define ZMQ_BUILD_DRAFT_API
#include "zmq.hpp"

using namespace std::chrono_literals;

// initialize the zmq context with a single IO thread
zmq::context_t context{1};

// construct a REP (reply) socket and bind to interface
zmq::socket_t socket{context, zmq::socket_type::dealer};

#ifdef __EMSCRIPTEN__
    #include <cassert>
    #include <emscripten.h>
#endif // __EMSCRIPTEN__

#include "AssetPackManager.h"
#include "Context.h"
#include "Editor.h"
#include "FileClassifier.h"
#include "Game.h"
#include "GameState.h"
#include "GameStateSnapshots.h"
#include "OpenRCT2.h"
#include "ParkImporter.h"
#include "PlatformEnvironment.h"
#include "ReplayManager.h"
#include "Version.h"
#include "actions/GameAction.h"
#include "audio/Audio.h"
#include "audio/AudioContext.h"
#include "config/Config.h"
#include "core/Console.hpp"
#include "core/File.h"
#include "core/FileScanner.h"
#include "core/FileStream.h"
#include "core/Guard.hpp"
#include "core/Http.h"
#include "core/MemoryStream.h"
#include "core/Path.hpp"
#include "core/String.hpp"
#include "core/Timer.hpp"
#include "drawing/IDrawingEngine.h"
#include "drawing/Image.h"
#include "drawing/LightFX.h"
#include "entity/EntityRegistry.h"
#include "entity/EntityTweener.h"
#include "interface/Chat.h"
#include "interface/StdInOutConsole.h"
#include "interface/Viewport.h"
#include "localisation/Formatter.h"
#include "localisation/Localisation.Date.h"
#include "localisation/LocalisationService.h"
#include "network/DiscordService.h"
#include "network/Network.h"
#include "network/NetworkBase.h"
#include "object/ObjectManager.h"
#include "object/ObjectRepository.h"
#include "paint/Painter.h"
#include "park/ParkFile.h"
#include "platform/Crash.h"
#include "platform/Platform.h"
#include "profiling/Profiling.h"
#include "rct2/RCT2.h"
#include "ride/TrackData.h"
#include "ride/TrackDesignRepository.h"
#include "scenario/ScenarioRepository.h"
#include "scenes/game/GameScene.h"
#include "scenes/intro/IntroScene.h"
#include "scenes/preloader/PreloaderScene.h"
#include "scenes/title/TitleScene.h"
#include "scenes/title/TitleSequenceManager.h"
#include "scripting/HookEngine.h"
#include "scripting/ScriptEngine.h"
#include "ui/UiContext.h"
#include "ui/WindowManager.h"
#include "world/MapAnimation.h"
#include "world/Park.h"

#include "object/TerrainEdgeObject.h"
#include "object/TerrainSurfaceObject.h"
#include "json/json.h"
#include "ride/Ride.h"
#include "ride/RideData.h"
#include "world/Scenery.h"
#include "world/Entrance.h"
#include "ride/Ride.h"
#include "rct2/T6Exporter.h"

#include "world/tile_element/SurfaceElement.h"
#include "world/tile_element/PathElement.h"
#include "world/tile_element/TrackElement.h"
#include "world/tile_element/WallElement.h"
#include "world/tile_element/SmallSceneryElement.h"
#include "world/tile_element/LargeSceneryElement.h"
#include "world/tile_element/EntranceElement.h"
#include "ride/RideManager.hpp"
//#include "world/Surface.h"

#include <chrono>
#include <cmath>
#include <exception>
#include <future>
#include <iterator>
#include <memory>
#include <string>
#include <sstream>
#include <iostream>
#include <iomanip>
#include <algorithm>

// New: verbose send helper to aid debugging of socket sends
namespace {
    static void VerboseSend(zmq::socket_t &sock, const std::string &address, const std::string &data)
    {
        try
        {
            sock.connect(address);
            bool sent = false;
            try
            {
                sent = static_cast<bool>(sock.send(zmq::buffer(data), zmq::send_flags::none));
            }
            catch (const std::exception &e)
            {
                std::cout << "[ZMQ SEND] exception while sending to " << address << ": " << e.what() << "\n";
            }

            if (sent)
            {
                std::cout << "[ZMQ SEND] success: sent " << data.size() << " bytes to " << address << "\n";
            }
            else
            {
                std::cout << "[ZMQ SEND] failed to send to " << address << " (send returned false)\n";
            }

            const size_t maxPreview = 200;
            const size_t show = std::min(data.size(), maxPreview);
            bool printable = true;
            for (size_t i = 0; i < show; ++i)
            {
                unsigned char c = static_cast<unsigned char>(data[i]);
                if (c < 32 && c != '\n' && c != '\r' && c != '\t')
                {
                    printable = false;
                    break;
                }
            }

            if (show > 0)
            {
                if (printable)
                {
                    std::cout << "[ZMQ SEND] data preview (first " << show << " bytes)\n";
                    std::cout << "----\n";
                    std::cout << data.substr(0, show) << (data.size() > show ? "...\n" : "\n");
                    std::cout << "----\n";
                }
                else
                {
                    std::ostringstream oss;
                    oss << std::hex << std::setfill('0');
                    for (size_t i = 0; i < show; ++i)
                    {
                        oss << std::setw(2) << static_cast<int>(static_cast<unsigned char>(data[i]));
                        if (i + 1 < show)
                            oss << ' ';
                    }
                    if (data.size() > show)
                        oss << " ...";
                    std::cout << "[ZMQ SEND] data (hex, first " << show << " bytes): " << oss.str() << "\n";
                }
            }

            try
            {
                //sock.disconnect(address);
            }
            catch (const std::exception &e)
            {
                std::cout << "[ZMQ SEND] exception while disconnecting from " << address << ": " << e.what() << "\n";
            }
        }
        catch (const std::exception &e)
        {
            std::cout << "[ZMQ SEND] unexpected exception: " << e.what() << "\n";
        }
    }
} // anonymous namespace

using namespace OpenRCT2;
using namespace OpenRCT2::Drawing;
using namespace OpenRCT2::Localisation;
using namespace OpenRCT2::Paint;
using namespace OpenRCT2::Scripting;
using namespace OpenRCT2::Ui;

using OpenRCT2::Audio::IAudioContext;

namespace OpenRCT2
{
    namespace
    {
        using namespace std::chrono_literals;

        static constexpr auto kForcedUpdateInterval = 25ms;
    } // namespace

    class Context final : public IContext
    {
    private:
        // Dependencies
        std::shared_ptr<IPlatformEnvironment> const _env;
        std::shared_ptr<IAudioContext> const _audioContext;
        std::shared_ptr<IUiContext> const _uiContext;

        // Services
        std::unique_ptr<LocalisationService> _localisationService;
        std::unique_ptr<IObjectRepository> _objectRepository;
        std::unique_ptr<IObjectManager> _objectManager;
        std::unique_ptr<ITrackDesignRepository> _trackDesignRepository;
        std::unique_ptr<IScenarioRepository> _scenarioRepository;
        std::unique_ptr<IReplayManager> _replayManager;
        std::unique_ptr<IGameStateSnapshots> _gameStateSnapshots;
        std::unique_ptr<AssetPackManager> _assetPackManager;
#ifdef __ENABLE_DISCORD__
        std::unique_ptr<DiscordService> _discordService;
#endif
        StdInOutConsole _stdInOutConsole;
#ifdef ENABLE_SCRIPTING
        ScriptEngine _scriptEngine;
#endif
#ifndef DISABLE_NETWORK
        NetworkBase _network;
#endif

        // Scenes
        std::unique_ptr<PreloaderScene> _preloaderScene;
        std::unique_ptr<IntroScene> _introScene;
        std::unique_ptr<TitleScene> _titleScene;
        std::unique_ptr<GameScene> _gameScene;
        IScene* _activeScene = nullptr;

        DrawingEngine _drawingEngineType = DrawingEngine::Software;
        std::unique_ptr<IDrawingEngine> _drawingEngine;
        std::unique_ptr<Painter> _painter;

        bool _initialised = false;

        Timer _timer;
        float _ticksAccumulator = 0.0f;
        float _realtimeAccumulator = 0.0f;
        float _timeScale = 1.0f;
        bool _variableFrame = false;

        // If set, will end the OpenRCT2 game loop. Intentionally private to this module so that the flag can not be set back to
        // false.
        bool _finished = false;

        std::future<void> _versionCheckFuture;
        NewVersionInfo _newVersionInfo;
        bool _hasNewVersionInfo = false;

        // We keep track of this to perform certain operations differently.
        std::thread::id _mainThreadId{};
        Timer _forcedUpdateTimer;

        BackgroundWorker _backgroundWorker;

    public:
        // Singleton of Context.
        // Remove this when GetContext() is no longer called so that
        // multiple instances can be created in parallel
        static Context* Instance;

    public:
        Context(
            const std::shared_ptr<IPlatformEnvironment>& env, const std::shared_ptr<IAudioContext>& audioContext,
            const std::shared_ptr<IUiContext>& uiContext)
            : _env(env)
            , _audioContext(audioContext)
            , _uiContext(uiContext)
            , _localisationService(std::make_unique<LocalisationService>(env))
            , _replayManager(CreateReplayManager())
            , _gameStateSnapshots(CreateGameStateSnapshots())
#ifdef ENABLE_SCRIPTING
            , _scriptEngine(_stdInOutConsole, *env)
#endif
#ifndef DISABLE_NETWORK
            , _network(*this)
#endif
            , _painter(std::make_unique<Painter>(uiContext))
        {
            // Can't have more than one context currently.
            Guard::Assert(Instance == nullptr);

            Instance = this;
            _mainThreadId = std::this_thread::get_id();
        }

        ~Context() override
        {
            // NOTE: We must shutdown all systems here before Instance is set back to null.
            //       If objects use GetContext() in their destructor things won't go well.

#ifdef ENABLE_SCRIPTING
            _scriptEngine.StopUnloadRegisterAllPlugins();
#endif

            GameActions::ClearQueue();
            _replayManager->StopRecording(true);
#ifndef DISABLE_NETWORK
            _network.Close();
#endif

            auto* windowMgr = Ui::GetWindowManager();
            windowMgr->CloseAll();

            // Unload objects after closing all windows, this is to overcome windows like
            // the object selection window which loads objects when closed.
            if (_objectManager != nullptr)
            {
                _objectManager->UnloadAll();
            }

            GfxObjectCheckAllImagesFreed();
            GfxUnloadCsg();
            GfxUnloadG2();
            GfxUnloadG1();
            Audio::Close();

            Instance = nullptr;
        }

        std::shared_ptr<IAudioContext> GetAudioContext() override
        {
            return _audioContext;
        }

        std::shared_ptr<IUiContext> GetUiContext() override
        {
            return _uiContext;
        }

#ifdef ENABLE_SCRIPTING
        Scripting::ScriptEngine& GetScriptEngine() override
        {
            return _scriptEngine;
        }
#endif

        std::shared_ptr<IPlatformEnvironment> GetPlatformEnvironment() override
        {
            return _env;
        }

        Localisation::LocalisationService& GetLocalisationService() override
        {
            return *_localisationService;
        }

        IObjectManager& GetObjectManager() override
        {
            return *_objectManager;
        }

        IObjectRepository& GetObjectRepository() override
        {
            return *_objectRepository;
        }

        ITrackDesignRepository* GetTrackDesignRepository() override
        {
            return _trackDesignRepository.get();
        }

        IScenarioRepository* GetScenarioRepository() override
        {
            return _scenarioRepository.get();
        }

        IReplayManager* GetReplayManager() override
        {
            return _replayManager.get();
        }

        IGameStateSnapshots* GetGameStateSnapshots() override
        {
            return _gameStateSnapshots.get();
        }

        AssetPackManager* GetAssetPackManager() override
        {
            return _assetPackManager.get();
        }

        DrawingEngine GetDrawingEngineType() override
        {
            return _drawingEngineType;
        }

        IDrawingEngine* GetDrawingEngine() override
        {
            return _drawingEngine.get();
        }

        Paint::Painter* GetPainter() override
        {
            return _painter.get();
        }

#ifndef DISABLE_NETWORK
        NetworkBase& GetNetwork() override
        {
            return _network;
        }
#endif

        int32_t RunOpenRCT2(int argc, const char** argv) override
        {
            if (Initialise())
            {
                Launch();
                return EXIT_SUCCESS;
            }
            return EXIT_FAILURE;
        }

        IScene* GetPreloaderScene() override
        {
            if (auto* scene = _preloaderScene.get())
                return scene;

            _preloaderScene = std::make_unique<PreloaderScene>(*this);
            return _preloaderScene.get();
        }

        IScene* GetIntroScene() override
        {
            if (auto* scene = _introScene.get())
                return scene;

            _introScene = std::make_unique<IntroScene>(*this);
            return _introScene.get();
        }

        IScene* GetTitleScene() override
        {
            if (auto* scene = _titleScene.get())
                return scene;

            _titleScene = std::make_unique<TitleScene>(*this);
            return _titleScene.get();
        }

        IScene* GetGameScene() override
        {
            if (auto* scene = _gameScene.get())
                return scene;

            _gameScene = std::make_unique<GameScene>(*this);
            return _gameScene.get();
        }

        IScene* GetEditorScene() override
        {
            // TODO: Implement me.
            return nullptr;
        }

        IScene* GetActiveScene() override
        {
            return _activeScene;
        }

        void SetActiveScene(IScene* screen) override
        {
            if (_activeScene != nullptr)
                _activeScene->Stop();
            _activeScene = screen;
            if (_activeScene)
                _activeScene->Load();
        }

        void WriteLine(const std::string& s) override
        {
            _stdInOutConsole.WriteLine(s);
        }

        void WriteErrorLine(const std::string& s) override
        {
            _stdInOutConsole.WriteLineError(s);
        }

        /**
         * Causes the OpenRCT2 game loop to finish.
         */
        void Finish() override
        {
            _finished = true;
        }

        void Quit() override
        {
            gSavePromptMode = PromptMode::quit;
            ContextOpenWindow(WindowClass::SavePrompt);
        }

        bool Initialise() final override
        {
            if (_initialised)
            {
                throw std::runtime_error("Context already initialised.");
            }
            _initialised = true;

            CrashInit();

            if (String::equals(Config::Get().general.LastRunVersion, kOpenRCT2Version))
            {
                gOpenRCT2ShowChangelog = false;
            }
            else
            {
                gOpenRCT2ShowChangelog = true;
                Config::Get().general.LastRunVersion = kOpenRCT2Version;
                Config::Save();
            }

            try
            {
                _localisationService->OpenLanguage(Config::Get().general.Language);
            }
            catch (const std::exception& e)
            {
                LOG_ERROR("Failed to open configured language: %s", e.what());
                try
                {
                    _localisationService->OpenLanguage(LANGUAGE_ENGLISH_UK);
                }
                catch (const std::exception& eFallback)
                {
                    LOG_FATAL("Failed to open fallback language: %s", eFallback.what());
                    auto uiContext = GetContext()->GetUiContext();
#ifdef __ANDROID__
                    uiContext->ShowMessageBox(
                        "You need to copy some additional files to finish your install.\n\nSee "
                        "https://docs.openrct2.io/en/latest/installing/installing-on-android.html for more details.");
#else
                    uiContext->ShowMessageBox("Failed to load language file!\nYour installation may be damaged.");
#endif
                    return false;
                }
            }

            // TODO add configuration option to allow multiple instances
            // if (!gOpenRCT2Headless && !Platform::LockSingleInstance()) {
            //  LOG_FATAL("OpenRCT2 is already running.");
            //  return false;
            // } //This comment was relocated so it would stay where it was in relation to the following lines of code.

            if (!gOpenRCT2Headless)
            {
                auto rct2InstallPath = GetOrPromptRCT2Path();
                if (rct2InstallPath.empty())
                {
                    return false;
                }
                _env->SetBasePath(DirBase::rct2, rct2InstallPath);
            }

            // The repositories are all dependent on the RCT2 path being set,
            // so they cannot be set in the constructor.
            _objectRepository = CreateObjectRepository(_env);
            _objectManager = CreateObjectManager(*_objectRepository);
            _trackDesignRepository = CreateTrackDesignRepository(_env);
            _scenarioRepository = CreateScenarioRepository(_env);

            if (!gOpenRCT2Headless)
            {
                _assetPackManager = std::make_unique<AssetPackManager>();
            }
#ifdef __ENABLE_DISCORD__
            if (!gOpenRCT2Headless)
            {
                _discordService = std::make_unique<DiscordService>();
            }
#endif

            if (Platform::ProcessIsElevated())
            {
                std::string elevationWarning = _localisationService->GetString(STR_ADMIN_NOT_RECOMMENDED);
                if (gOpenRCT2Headless)
                {
                    Console::Error::WriteLine(elevationWarning.c_str());
                }
                else
                {
                    _uiContext->ShowMessageBox(elevationWarning);
                }
            }

            if (Platform::IsRunningInWine())
            {
                std::string wineWarning = _localisationService->GetString(STR_WINE_NOT_RECOMMENDED);
                if (gOpenRCT2Headless)
                {
                    Console::Error::WriteLine(wineWarning.c_str());
                }
                else
                {
                    _uiContext->ShowMessageBox(wineWarning);
                }
            }

            if (!gOpenRCT2Headless)
            {
                _uiContext->CreateWindow();
            }

            EnsureUserContentDirectoriesExist();

            if (!gOpenRCT2Headless)
            {
                Audio::Init();
                Audio::PopulateDevices();
                Audio::InitRideSoundsAndInfo();
                Audio::gGameSoundsOff = !Config::Get().sound.MasterSoundEnabled;
            }

            ChatInit();
            CopyOriginalUserFilesOver();

            if (!gOpenRCT2NoGraphics)
            {
                if (!LoadBaseGraphics())
                {
                    return false;
                }
                Drawing::LightFx::Init();
            }

            ViewportInitAll();

            ContextInit();

            if (!gOpenRCT2Headless)
            {
                auto* preloaderScene = static_cast<PreloaderScene*>(GetPreloaderScene());
                SetActiveScene(preloaderScene);

                // TODO: preload the title scene in another (parallel) job.
                preloaderScene->AddJob([this]() { InitialiseRepositories(); });
                preloaderScene->AddJob([this]() { InitialiseScriptEngine(); });
            }
            else
            {
                InitialiseRepositories();
                InitialiseScriptEngine();
            }

            return true;
        }

    private:
        void InitialiseRepositories()
        {
            if (!_initialised)
            {
                throw std::runtime_error("Context needs to be initialised first.");
            }

            auto currentLanguage = _localisationService->GetCurrentLanguage();

            OpenProgress(STR_CHECKING_OBJECT_FILES);
            _objectRepository->LoadOrConstruct(currentLanguage);

            OpenProgress(STR_LOADING_GENERIC);
            Audio::LoadAudioObjects();

            if (!gOpenRCT2Headless)
            {
                OpenProgress(STR_CHECKING_ASSET_PACKS);
                _assetPackManager->Scan();
                _assetPackManager->LoadEnabledAssetPacks();
                _assetPackManager->Reload();
            }

            OpenProgress(STR_CHECKING_TRACK_DESIGN_FILES);
            _trackDesignRepository->Scan(currentLanguage);

            OpenProgress(STR_CHECKING_SCENARIO_FILES);
            _scenarioRepository->Scan(currentLanguage);

            OpenProgress(STR_CHECKING_TITLE_SEQUENCES);
            TitleSequenceManager::Scan();

            OpenProgress(STR_LOADING_GENERIC);
        }

        void InitialiseScriptEngine()
        {
#ifdef ENABLE_SCRIPTING
            OpenProgress(STR_LOADING_PLUGIN_ENGINE);
            _scriptEngine.Initialise();
            _uiContext->InitialiseScriptExtensions();

            OpenProgress(STR_LOADING_GENERIC);
#endif
        }

    public:
        void InitialiseDrawingEngine() final override
        {
            assert(_drawingEngine == nullptr);

            _drawingEngineType = Config::Get().general.DrawingEngine;

            auto drawingEngineFactory = _uiContext->GetDrawingEngineFactory();
            auto drawingEngine = drawingEngineFactory->Create(_drawingEngineType, _uiContext);

            if (drawingEngine == nullptr)
            {
                if (_drawingEngineType == DrawingEngine::Software)
                {
                    _drawingEngineType = DrawingEngine::None;
                    LOG_FATAL("Unable to create a drawing engine.");
                    exit(-1);
                }
                else
                {
                    LOG_ERROR("Unable to create drawing engine. Falling back to software.");

                    // Fallback to software
                    Config::Get().general.DrawingEngine = DrawingEngine::Software;
                    Config::Save();
                    DrawingEngineInit();
                }
            }
            else
            {
                try
                {
                    drawingEngine->Initialise();
                    drawingEngine->SetVSync(Config::Get().general.UseVSync);
                    _drawingEngine = std::move(drawingEngine);
                }
                catch (const std::exception& ex)
                {
                    if (_drawingEngineType == DrawingEngine::Software)
                    {
                        _drawingEngineType = DrawingEngine::None;
                        LOG_ERROR(ex.what());
                        LOG_FATAL("Unable to initialise a drawing engine.");
                        exit(-1);
                    }
                    else
                    {
                        LOG_ERROR(ex.what());
                        LOG_ERROR("Unable to initialise drawing engine. Falling back to software.");

                        // Fallback to software
                        Config::Get().general.DrawingEngine = DrawingEngine::Software;
                        Config::Save();
                        DrawingEngineInit();
                    }
                }
            }

            WindowCheckAllValidZoom();
        }

        void DisposeDrawingEngine() final override
        {
            _drawingEngine = nullptr;
        }

        void OpenProgress(StringId captionStringId) override
        {
            auto captionString = _localisationService->GetString(captionStringId);
            auto intent = Intent(INTENT_ACTION_PROGRESS_OPEN);
            intent.PutExtra(INTENT_EXTRA_MESSAGE, captionString);
            ContextOpenIntent(&intent);
        }

        void SetProgress(uint32_t currentProgress, uint32_t totalCount, StringId format = kStringIdNone) override
        {
            if (_forcedUpdateTimer.GetElapsedTime() < kForcedUpdateInterval)
                return;

            _forcedUpdateTimer.Restart();

            auto intent = Intent(INTENT_ACTION_PROGRESS_SET);
            intent.PutExtra(INTENT_EXTRA_PROGRESS_OFFSET, currentProgress);
            intent.PutExtra(INTENT_EXTRA_PROGRESS_TOTAL, totalCount);
            intent.PutExtra(INTENT_EXTRA_STRING_ID, format);
            ContextOpenIntent(&intent);

            // When we call this from the main thread we can pump messages and redraw.
            const auto isMainThread = _mainThreadId == std::this_thread::get_id();

            if (!gOpenRCT2Headless && isMainThread)
            {
                _uiContext->ProcessMessages();
                auto* windowMgr = Ui::GetWindowManager();
                windowMgr->InvalidateByClass(WindowClass::ProgressWindow);
                Draw();
            }
        }

        void CloseProgress() override
        {
            auto intent = Intent(INTENT_ACTION_PROGRESS_CLOSE);
            ContextOpenIntent(&intent);
        }

        bool LoadParkFromFile(const u8string& path, bool loadTitleScreenOnFail = false, bool asScenario = false, bool sendOverSocket = true) final override
        {
            LOG_VERBOSE("Context::LoadParkFromFile(%s)", path.c_str());

            struct CrashAdditionalFileRegistration
            {
                CrashAdditionalFileRegistration(const std::string& path)
                {
                    // Register the file for crash upload if it asserts while loading.
                    CrashRegisterAdditionalFile("load_park", path);
                }
                ~CrashAdditionalFileRegistration()
                {
                    // Deregister park file in case it was processed without hitting an assert.
                    CrashUnregisterAdditionalFile("load_park");
                }
            } crash_additional_file_registration(path);

            //try
            {
                if (String::iequals(Path::GetExtension(path), ".sea"))
                {
                    auto data = DecryptSea(fs::u8path(path));
                    auto ms = MemoryStream(data.data(), data.size(), MEMORY_ACCESS::READ);
                    if (!LoadParkFromStream(&ms, path, loadTitleScreenOnFail, asScenario))
                    {
                        throw std::runtime_error(".sea file may have been renamed.");
                    }
                    return true;
                }

                auto fs = FileStream(path, FileMode::open);
                if (!LoadParkFromStream(&fs, path, loadTitleScreenOnFail, asScenario))
                {
                    return false;
                }
				
			    Json::Value event;
				
			    auto& gameState = OpenRCT2::getGameState();
				event["map_size"]["x"] = gameState.mapSize.x;
				event["map_size"]["y"] = gameState.mapSize.y;
				event["park_size"] = gameState.park.Size;
				event["scenario_type"] = gameState.scenarioObjective.Type;
				event["objective_num_months"] = MONTH_COUNT * gameState.scenarioObjective.Year;
				event["objective_num_guests"] = gameState.scenarioObjective.NumGuests;
				event["free_entry"] = gameState.park.Flags & PARK_FLAGS_PARK_FREE_ENTRY;
				event["flags"] = gameState.park.Flags;
				
				//std::cout<<"start\n";
				
				//event["spawns"] = 
				for (auto& spawn : gameState.peepSpawns)
				{
					Json::Value spawn_j;
					spawn_j["x"] = spawn.x;
					spawn_j["y"] = spawn.y;
					spawn_j["z"] = spawn.z;
					spawn_j["direction"] = spawn.direction;
					event["spawns"].append(spawn_j);
				}
				
				for (auto& spawn : gameState.park.Entrances)
				{
					Json::Value spawn_j;
					spawn_j["x"] = spawn.x;
					spawn_j["y"] = spawn.y;
					spawn_j["z"] = spawn.z;
					spawn_j["direction"] = spawn.direction;
					event["entrances"].append(spawn_j);
				}
				
			    auto& objectMgr = OpenRCT2::GetContext()->GetObjectManager();
				
				std::set<Json::Value> objectIDs;
				std::set<Json::Value> legacyObjectIDs;
				
				// rides
	            for (auto& ride : GetRideManager())
				{
					if (ride.status == RideStatus::closed)
					{
						continue;
					}
					Json::Value ride_j;
					
					ride_j["type"] = ride.type;
				    auto obj = static_cast<RideObject*>(objectMgr.GetLoadedObject(ObjectType::ride, ride.subtype));
					if (obj != nullptr)
					{
						ride_j["subtype_obj_id"] = std::string(obj->GetIdentifier());
						ride_j["subtype_obj_id_legacy"] = std::string(obj->GetLegacyIdentifier());
					}
					ride_j["mode"] = static_cast<uint8_t>(ride.mode);					
					ride_j["name"] = ride.getName();
					
					//ride_j["subtype"] = ride->subtype;
					

		            for (StationIndex::UnderlyingType s = 0; s < Limits::kMaxStationsPerRide; s++)
		            {
		                StationIndex stationIndex = StationIndex::FromUnderlying(s);
		                auto& station = ride.getStation(stationIndex);
						
						Json::Value station_j;
		                if (station.Start.IsNull() && station.Entrance.IsNull() && station.Exit.IsNull())
						{
							continue;
						}

		                if (station.Start.IsNull())
		                {
							station_j["station_start"] = "null";
		                }
		                else
		                {
							station_j["station_start_x"] = station.Start.x;
							station_j["station_start_y"] = station.Start.y;
		                }
		                station_j["Height"] = station.Height;
		                station_j["Length"] = station.Length;
		                station_j["Depart"] = station.Depart;

		                if (station.Entrance.IsNull())
							station_j["entrance"] = "null";
		                else
						{
							station_j["entrance_pos"]["x"] = station.Entrance.x;// station->entrances[i].x;
							station_j["entrance_pos"]["y"] = station.Entrance.z;//->entrances[i].y;
							station_j["entrance_pos"]["z"] = station.Entrance.z;//->station_heights[i];
						}

		                if (station.Exit.IsNull())
							station_j["exit"] = "null";
		                else
						{
							station_j["exit_pos"]["x"] = station.Exit.x;//->exits[i].x;
							station_j["exit_pos"]["y"] = station.Exit.y;//->exits[i].y;
							station_j["exit_pos"]["z"] = station.Exit.z;//->station_heights[i];
						}
						ride_j["stations"].append(station_j);
					}
					
					// save track design, if applicable.
					/*
				    TrackDesignState tds{};
					std::string trackFile = "none";
				    auto _trackDesign = ride->SaveToTrackDesign(tds);
				    if (!_trackDesign)
				    {
						std::cout<<"cant get design for ride\n";
				        //return;
				    }
					//else if (curRide->custom_name != "Test")
					else
					{
				        auto errMessage = _trackDesign->CreateTrackDesignScenery(tds);
				        if (errMessage != STR_NONE)
				        {
				            context_show_error(STR_CANT_SAVE_TRACK_DESIGN, errMessage, {});
							std::cout<<"cant save1\n";
				        }
						//}
						else
						{
						    char pathBuffer[100];
							// todo: add cur time in seconds to string plus random number
							auto randomNumber = scenario_rand() % 100;
							
					        std::stringstream stream;
							stream << "exported/" << gScenarioName << "-...-" << ride->GetName() << "-...-" << randomNumber << ".td6";
						    std::string withExtension = stream.str(); //  "export.td6"; // Path::WithExtension(, "td6");
						    String::Set(pathBuffer, sizeof(pathBuffer), withExtension.c_str());

						    RCT2::T6Exporter t6Export{ _trackDesign.get() };

						    auto success = t6Export.SaveTrack(pathBuffer);

						    if (!success)
						    {
								std::cout<<"err saving\n";
						    }
							else
							{
								trackFile = withExtension;
								std::cout<<"success saving ride\n";
							}
						}
					}
					ride_j["track_file"] = trackFile;
					*/
					event["rides"].append(ride_j);
				}
				
			    TileElementIterator iter;
			    TileElementIteratorBegin(&iter);
			    do
			    {
					// check if surface is owned or not.
					bool owned = false;
					auto surface = MapGetSurfaceElementAt(TileCoordsXY{ iter.x, iter.y });
					if ((surface->GetOwnership() & OWNERSHIP_OWNED) || (surface->GetOwnership() & OWNERSHIP_CONSTRUCTION_RIGHTS_OWNED))
						owned = true;
					
					/*
				    TileElementIterator cur_iter;
					cur_iter.x = iter.x;
					cur_iter.y = iter.y;
			        cur_iter.element = MapGetFirstElementAt(TileCoordsXY{ iter.x, iter.y });
					do {
						TileElement* cur_element = cur_iter.element;
						if (cur_element->GetType() == TileElementType::Surface)
						{
							auto surfaceEl = cur_element->AsSurface();
							if ((surfaceEl->GetOwnership() & OWNERSHIP_OWNED))
							{
								owned = true;
							}
							break;
						}
					} while(!(cur_iter.element++)->IsLastForTile());
					
					if (cur_iter.x == iter.x and cur_iter.y == iter.y and !owned)
					{
						continue;
					}*/
					
					TileElement* element = iter.element;
					
					if (element->GetBaseZ() == 16 && element->GetType() == TileElementType::Surface)
					{
						continue;
						//auto surfaceEl = iter.element->AsSurface();
						//if (surfaceEl->GetOwnership() & OWNERSHIP_OWNED)
						//	continue; // if owned, skip
					}
					if (element->GetType() == TileElementType::Banner)
					{
						continue;
					}
	
					std::string x, y, z;

					x = std::to_string(iter.x);
					y = std::to_string(iter.y);
					
					auto sz = event["map"][x][y].size();
					
					Json::Value cur_field;
					cur_field["type"] = static_cast<uint8_t>(element->GetType());
					cur_field["direction"] = static_cast<uint8_t>(element->GetDirection());
					cur_field["base_z"] = static_cast<int32_t>(element->GetBaseZ());
					cur_field["clearance_z"] = static_cast<int32_t>(element->GetClearanceZ());
					cur_field["quadrants"] = static_cast<uint8_t>(element->GetOccupiedQuadrants());
					cur_field["owned"] = owned;
					//cur_field["owned_by_park"] = map_is_location_owned_or_has_rights(CoordsXY({iter.x, iter.y})); // bool
	
					switch(iter.element->GetType()) // uint8_t
					{
					    case TileElementType::Surface:
						{ // Surface.cpp
							//std::cout<<"1\n";
			                
							auto surfaceEl = iter.element->AsSurface();
							
							cur_field["slope"] = static_cast<uint8_t>(surfaceEl->GetSlope());
							//if (surfaceEl->GetOwnership() & OWNERSHIP_OWNED)
							//	cur_field["owned_by_park"] = true;
							//else cur_field["owned_by_park"] = false;
							
			                auto surfaceIndex = surfaceEl->GetSurfaceObjectIndex(); //Style(); // uint32_t
			                auto edgeIndex = surfaceEl->GetEdgeObjectIndex(); //Style(); // uint32_t
							//cur_field["surface_style"] = surfaceIndex;
							//cur_field["edge_style"] = edgeIndex;
							
					        auto surfaceObj = static_cast<TerrainSurfaceObject*>(objectMgr.GetLoadedObject(ObjectType::terrainSurface, surfaceIndex));
					        auto edgeObj = static_cast<TerrainEdgeObject*>(objectMgr.GetLoadedObject(ObjectType::terrainEdge, edgeIndex));
							
							if (surfaceObj != nullptr)
							{
								cur_field["surface_obj_id"] = std::string(surfaceObj->GetIdentifier());
								cur_field["surface_obj_id_legacy"] = std::string(surfaceObj->GetLegacyIdentifier());
								
								Json::Value id;
								id["id"] = std::string(surfaceObj->GetIdentifier());
								id["type"] = static_cast<uint8_t>(ObjectType::terrainSurface);
								objectIDs.insert(id);
								
								Json::Value lId;
								lId["id"] = std::string(surfaceObj->GetLegacyIdentifier());
								lId["type"] = static_cast<uint8_t>(ObjectType::terrainSurface);
								legacyObjectIDs.insert(lId);
							}
							if (edgeObj != nullptr)
							{
								cur_field["edge_obj_id"] = std::string(edgeObj->GetIdentifier());
								cur_field["edge_obj_id_legacy"] = std::string(edgeObj->GetLegacyIdentifier());
								
								Json::Value id;
								id["id"] = std::string(edgeObj->GetIdentifier());
								id["type"] = static_cast<uint8_t>(ObjectType::terrainEdge);
								objectIDs.insert(id);
								
								Json::Value lId;
								lId["id"] = std::string(edgeObj->GetLegacyIdentifier());
								lId["type"] = static_cast<uint8_t>(ObjectType::terrainEdge);
								legacyObjectIDs.insert(lId);
							}
							cur_field["water_height"] = static_cast<int32_t>(surfaceEl->GetWaterHeight());
			
							break;
						}
					    case TileElementType::Path:
						{
							//std::cout<<"2\n";
							
							auto pathEl = iter.element->AsPath();
							
							auto footpathObj = pathEl->GetLegacyPathEntry();
							if (footpathObj == nullptr)
							{
								cur_field["legacy"] = false;
								auto surfaceEntryIndex = pathEl->GetSurfaceEntryIndex();
								auto railingEntryIndex = pathEl->GetRailingsEntryIndex();
							    auto surfaceObj = objectMgr.GetLoadedObject(ObjectType::footpathSurface, surfaceEntryIndex);
							    auto railingObj = objectMgr.GetLoadedObject(ObjectType::footpathRailings, railingEntryIndex);
								//cur_field["surface_entry_index"] = surfaceEntryIndex;
								//cur_field["railing_entry_index"] = railingEntryIndex;
								if (surfaceObj != nullptr)
								{
									cur_field["surface_obj_id"] = std::string(surfaceObj->GetIdentifier());
									cur_field["surface_obj_id_legacy"] = std::string(surfaceObj->GetLegacyIdentifier());
									
									Json::Value id;
									id["id"] = std::string(surfaceObj->GetIdentifier());
									id["type"] = static_cast<uint8_t>(ObjectType::footpathSurface);
									objectIDs.insert(id);
								
									//Json::Value lId;
									//lId["id"] = std::string(surfaceObj->GetLegacyIdentifier());
									//lId["type"] = static_cast<uint8_t>(element->GetType());;
									//legacyObjectIDs.insert(lId);
								}
								if (railingObj != nullptr)
								{
									cur_field["railing_obj_id"] = std::string(railingObj->GetIdentifier());
									cur_field["railing_obj_id_legacy"] = std::string(railingObj->GetLegacyIdentifier());
									
									Json::Value id;
									id["id"] = std::string(railingObj->GetIdentifier());
									id["type"] = static_cast<uint8_t>(ObjectType::footpathRailings);
									objectIDs.insert(id);
								
									//Json::Value lId;
									//lId["id"] = std::string(railingObj->GetLegacyIdentifier());
									//lId["type"] = static_cast<uint8_t>(element->GetType());;
									//legacyObjectIDs.insert(lId);
								}
							}
							else
							{
								cur_field["legacy"] = true;
								//cur_field["entry_index"] = pathEl->GetLegacyPathEntryIndex();
								// TODO
							}
							
							cur_field["sloped"] = pathEl->IsSloped();
							cur_field["slope_direction"] = pathEl->GetSlopeDirection();
							cur_field["queue"] = pathEl->IsQueue(); // bool
							cur_field["ride_index"] = pathEl->GetRideIndex().ToUnderlying();
							cur_field["station_index"] = pathEl->GetStationIndex().ToUnderlying();
							cur_field["edges"] = pathEl->GetEdges();
							
							break;
						}
					    case TileElementType::Track:
						{
							//std::cout<<"3\n";
							
							auto trackEl = iter.element->AsTrack();
							auto rideIndex = trackEl->GetRideIndex(); // RideId -> TIdentifier<uint16_t, std::numeric_limits<uint16_t>::max(), struct RideIdTag>;
			
							Ride* ride = GetRide(rideIndex);
							cur_field["ride_name"] = ride->getName();
							cur_field["ride_type"] = ride->type;
							cur_field["track_type"] = static_cast<uint16_t>(trackEl->GetTrackType()); // track_type_t -> uint16_t
							cur_field["sequence_index"] = trackEl->GetSequenceIndex();
							cur_field["ride_index"] = static_cast<uint16_t>(trackEl->GetRideIndex().ToUnderlying());
							cur_field["has_chain"] = trackEl->HasChain();
							cur_field["has_cable_lift"] = trackEl->HasCableLift();
							cur_field["is_inverted"] = trackEl->IsInverted();
							cur_field["station_index"] = static_cast<uint8_t>(trackEl->GetStationIndex().ToUnderlying());
							
							cur_field["excitement"] = ride->ratings.excitement;
							cur_field["intensity"] = ride->ratings.intensity;
							cur_field["nausea"] = ride->ratings.nausea;
							
							//auto name_string_id = ride->GetRideTypeDescriptor().Naming.Name;
						    //Formatter ft;
						    //auto titlez = format_string(name_string_id, ft.Data());
							//cur_field["default_ride_name"] = titlez;
										
						    auto obj = static_cast<RideObject*>(objectMgr.GetLoadedObject(ObjectType::ride, ride->subtype));
							if (obj != nullptr)
							{
								cur_field["subtype_obj_id"] = std::string(obj->GetIdentifier());
								cur_field["subtype_obj_id_legacy"] = std::string(obj->GetLegacyIdentifier());
								
								Json::Value id;
								id["id"] = std::string(obj->GetIdentifier());
								id["type"] = static_cast<uint8_t>(ObjectType::ride);
								objectIDs.insert(id);
								
								Json::Value lId;
								lId["id"] = std::string(obj->GetLegacyIdentifier());
								lId["type"] = static_cast<uint8_t>(ObjectType::ride);
								legacyObjectIDs.insert(lId);
							}
							
				            auto ride_entry = GetRideEntryByIndex(ride->subtype);
				            if (ride_entry != nullptr)
							{
					            if (ride_entry->shop_item[1] != ShopItem::None)
					            {
					                money16 price = ride->price[1];
									ShopItem shop_item = ride_entry->shop_item[1];
									cur_field["shop_item_price_1"] = price;
									cur_field["shop_item_type_1"] = static_cast<uint8_t>(shop_item);
					            }
					            if (ride_entry->shop_item[0] != ShopItem::None)
					            {
					                money16 price = ride->price[0];
									ShopItem shop_item = ride_entry->shop_item[0];
									cur_field["shop_item_price_0"] = price;
									cur_field["shop_item_type_0"] = static_cast<uint8_t>(shop_item);
					            }
							}
							
							break;
						}
					    case TileElementType::SmallScenery:
						{
							//std::cout<<"4\n";

							auto sceneryEl = iter.element->AsSmallScenery();			
							auto entryIndex = sceneryEl->GetEntryIndex(); // ObjectEntryIndex
						    auto obj = objectMgr.GetLoadedObject(ObjectType::smallScenery, entryIndex);
							if (obj != nullptr)
							{
								cur_field["obj_id"] = std::string(obj->GetIdentifier());
								cur_field["obj_id_legacy"] = std::string(obj->GetLegacyIdentifier());
								
								Json::Value id;
								id["id"] = std::string(obj->GetIdentifier());
								id["type"] = static_cast<uint8_t>(ObjectType::smallScenery);
								objectIDs.insert(id);
								
								Json::Value lId;
								lId["id"] = std::string(obj->GetLegacyIdentifier());
								lId["type"] = static_cast<uint8_t>(ObjectType::smallScenery);
								legacyObjectIDs.insert(lId);
							}
							//cur_field["entry_index"] = sceneryEl->GetEntryIndex();
							cur_field["scenery_quadrant"] = sceneryEl->GetSceneryQuadrant();
							cur_field["primary_colour"] = sceneryEl->GetPrimaryColour();
							cur_field["secondary_colour"] = sceneryEl->GetSecondaryColour();
							
							break;
						}
					    case TileElementType::Entrance:
						{
							auto entranceEl = iter.element->AsEntrance();
			
							cur_field["entranceType"] = entranceEl->GetEntranceType();
							cur_field["station_index"] = static_cast<uint8_t>(entranceEl->GetStationIndex().ToUnderlying());
							cur_field["sequence_index"] = entranceEl->GetSequenceIndex();
			
							auto rideIndex = entranceEl->GetRideIndex();
							cur_field["ride_index"] = static_cast<uint16_t>(rideIndex.ToUnderlying());

							Ride* ride = GetRide(rideIndex);
							if (ride != nullptr)
							{
								cur_field["ride_name"] = ride->getName();
								cur_field["ride_type"] = ride->type;
								cur_field["excitement"] = ride->ratings.excitement;
								cur_field["intensity"] = ride->ratings.intensity;
								cur_field["nausea"] = ride->ratings.nausea;
							}
							break;
						}
					    case TileElementType::Wall:
						{
							//std::cout<<"5\n";
							
							auto wallEl = iter.element->AsWall();			
							auto entryIndex = wallEl->GetEntryIndex(); // ObjectEntryIndex
						    auto obj = objectMgr.GetLoadedObject(ObjectType::walls, entryIndex);
							
							if (obj != nullptr)
							{
								cur_field["obj_id"] = std::string(obj->GetIdentifier());
								cur_field["obj_id_legacy"] = std::string(obj->GetLegacyIdentifier());
								
								Json::Value id;
								id["id"] = std::string(obj->GetIdentifier());
								id["type"] = static_cast<uint8_t>(ObjectType::walls);
								objectIDs.insert(id);
								
								Json::Value lId;
								lId["id"] = std::string(obj->GetLegacyIdentifier());
								lId["type"] = static_cast<uint8_t>(ObjectType::walls);
								legacyObjectIDs.insert(lId);
							}
							//cur_field["entry_index"] = wallEl->GetEntryIndex();
							cur_field["slope"] = static_cast<uint8_t>(wallEl->GetSlope());
							cur_field["primary_colour"] = wallEl->GetPrimaryColour();
							cur_field["secondary_colour"] = wallEl->GetSecondaryColour();
							cur_field["tertiary_colour"] = wallEl->GetTertiaryColour();
							
							break;
						}
					    case TileElementType::LargeScenery:
						{
							//std::cout<<"6\n";

							auto sceneryEl = iter.element->AsLargeScenery();			
							auto entryIndex = sceneryEl->GetEntryIndex(); // ObjectEntryIndex
						    auto obj = objectMgr.GetLoadedObject(ObjectType::largeScenery, entryIndex);
							
							if (obj != nullptr)
							{
								cur_field["obj_id"] = std::string(obj->GetIdentifier());
								cur_field["obj_id_legacy"] = std::string(obj->GetLegacyIdentifier());
								
								Json::Value id;
								id["id"] = std::string(obj->GetIdentifier());
								id["type"] = static_cast<uint8_t>(ObjectType::largeScenery);
								objectIDs.insert(id);
								
								Json::Value lId;
								lId["id"] = std::string(obj->GetLegacyIdentifier());
								lId["type"] = static_cast<uint8_t>(ObjectType::largeScenery);
								legacyObjectIDs.insert(lId);
							}
							//cur_field["entry_index"] = sceneryEl->GetEntryIndex();
							cur_field["sequence_index"] = sceneryEl->GetSequenceIndex();
							cur_field["primary_colour"] = sceneryEl->GetPrimaryColour();
							cur_field["secondary_colour"] = sceneryEl->GetSecondaryColour();
							
							break;
						}
					    case TileElementType::Banner:
						{
							// TODO
							//auto banner = iter.element->AsBanner();
							//auto banner2 = banner->GetBanner();
						    //auto obj = objectMgr.GetLoadedObject(ObjectType::Banners, banner->type);
							//cur_field["obj_id"] = std::string(obj->GetIdentifier());
							//cur_field["obj_id_legacy"] = std::string(obj->GetLegacyIdentifier());
							//break;
						}
					}
			
			    	event["map"][x][y].append(cur_field);
				} while (TileElementIteratorNext(&iter));
				
				for (auto &id : objectIDs)
					event["object_ids"].append(id);
				
				for (auto &id : legacyObjectIDs)
					event["legacy_object_ids"].append(id);
				
				if (sendOverSocket)
				{
					std::cout<<"trying to send\n";
				        ;
				    Json::StyledWriter styledWriter;
					VerboseSend(socket, portAddress2, styledWriter.write(event));
				}
				//std::cout<<"sent json\n";
				
				/*
				std::ofstream park_file;
				park_file.open("park.json");
				park_file << styledWriter.write(event);
				park_file.close();
				*/
				
                return true;
            }
            /*catch (const std::exception& e)
            {
                Console::Error::WriteLine(e.what());
                if (loadTitleScreenOnFail)
                {
                    SetActiveScene(GetTitleScene());
                }
                auto windowManager = _uiContext->GetWindowManager();
				
				std::cout <<" error loading ***:" << e.what() << "\n";
				
				socket.connect(portAddress2);
				const std::string error{e.what()};
				socket.send(zmq::buffer(error), zmq::send_flags::none);
				socket.disconnect(portAddress2);
				//std::cout<<"sent error\n";
			
                windowManager->ShowError(STR_FAILED_TO_LOAD_FILE_CONTAINS_INVALID_DATA, kStringIdNone, {});
            }*/
            return false;
        }

        bool LoadParkFromStream(
            IStream* stream, const std::string& path, bool loadTitleScreenFirstOnFail = false,
            bool asScenario = false) final override
        {
            try
            {
				bool jsonType = false;
                ClassifiedFileInfo info;
                if (String::equals(Path::GetExtension(path).c_str(), ".json", true))
				{
					//std::cout<<"json file\n";
					jsonType = true;
				}
				else
				{
	                if (!TryClassifyFile(stream, &info))
	                {
	                    throw std::runtime_error("Unable to detect file type");
	                }

	                if (info.Type != FileType::park && info.Type != FileType::savedGame && info.Type != FileType::scenario)
	                {
	                    throw std::runtime_error("Invalid file type.");
	                }
				}
                std::unique_ptr<IParkImporter> parkImporter;
				if (jsonType)
				{
					parkImporter = ParkImporter::CreateJson(*_objectRepository);
				}
                else if (info.Type == FileType::park)
                {
                    parkImporter = ParkImporter::CreateParkFile(*_objectRepository);
                }
                else if (info.Version <= kFileTypeS4Cutoff)
                {
                    // Save is an S4 (RCT1 format)
                    parkImporter = ParkImporter::CreateS4();
                }
                else
                {
                    // Save is an S6 (RCT2 format)
                    parkImporter = ParkImporter::CreateS6(*_objectRepository);
                }

                // Inhibit viewport rendering while we're loading
                WindowSetFlagForAllViewports(VIEWPORT_FLAG_RENDERING_INHIBITED, true);

                OpenProgress(asScenario ? STR_LOADING_SCENARIO : STR_LOADING_SAVED_GAME);
                SetProgress(0, 100, STR_STRING_M_PERCENT);

                auto result = parkImporter->LoadFromStream(stream, !jsonType && info.Type == FileType::scenario, false, path.c_str());
                SetProgress(10, 100, STR_STRING_M_PERCENT);

                // From this point onwards the currently loaded park will be corrupted if loading fails
                // so reload the title screen if that happens.
                loadTitleScreenFirstOnFail = true;

                GameUnloadScripts();
                _objectManager->LoadObjects(result.RequiredObjects, true);
                SetProgress(90, 100, STR_STRING_M_PERCENT);

                // TODO: Have a separate GameState and exchange once loaded.
                auto& gameState = ::getGameState();
                parkImporter->Import(gameState);
                SetProgress(100, 100, STR_STRING_M_PERCENT);

                // Reset viewport rendering inhibition
                WindowSetFlagForAllViewports(VIEWPORT_FLAG_RENDERING_INHIBITED, false);

                gScenarioSavePath = path;
                gCurrentLoadedPath = path;
                gFirstTimeSaving = true;
                GameFixSaveVars();
                MapAnimationAutoCreate();
                EntityTweener::Get().Reset();
                gScreenAge = 0;
                gLastAutoSaveUpdate = kAutosavePause;

#ifndef DISABLE_NETWORK
                bool sendMap = false;
#endif
                if (!asScenario && (jsonType || info.Type == FileType::park || info.Type == FileType::savedGame))
                {
#ifndef DISABLE_NETWORK
                    if (_network.GetMode() == NETWORK_MODE_CLIENT)
                    {
                        _network.Close();
                    }
#endif
                    GameLoadInit();
#ifndef DISABLE_NETWORK
                    if (_network.GetMode() == NETWORK_MODE_SERVER)
                    {
                        sendMap = true;
                    }
#endif
                }
                else
                {
                    ScenarioBegin(gameState);
#ifndef DISABLE_NETWORK
                    if (_network.GetMode() == NETWORK_MODE_SERVER)
                    {
                        sendMap = true;
                    }
                    if (_network.GetMode() == NETWORK_MODE_CLIENT)
                    {
                        _network.Close();
                    }
#endif
                }
                // This ensures that the newly loaded save reflects the user's
                // 'show real names of guests' option, now that it's a global setting
                PeepUpdateNames();
#ifndef DISABLE_NETWORK
                if (sendMap)
                {
                    _network.ServerSendMap();
                }
#endif

#ifdef USE_BREAKPAD
                if (_network.GetMode() == NETWORK_MODE_NONE)
                {
                    StartSilentRecord();
                }
#endif
                if (result.SemiCompatibleVersion)
                {
                    auto windowManager = _uiContext->GetWindowManager();
                    auto ft = Formatter();
                    ft.Add<uint32_t>(result.TargetVersion);
                    ft.Add<uint32_t>(OpenRCT2::kParkFileCurrentVersion);
                    windowManager->ShowError(STR_WARNING_PARK_VERSION_TITLE, STR_WARNING_PARK_VERSION_MESSAGE, ft);
                }
                else if (HasObjectsThatUseFallbackImages())
                {
                    Console::Error::WriteLine("Park has objects which require RCT1 linked. Fallback images will be used.");
                    auto windowManager = _uiContext->GetWindowManager();
                    windowManager->ShowError(STR_PARK_USES_FALLBACK_IMAGES_WARNING, kStringIdEmpty, Formatter());
                }

                CloseProgress();
                return true;
            }
            catch (const ObjectLoadException& e)
            {
                Console::Error::WriteLine("Unable to open park: missing objects");
				std::cout <<" error loading D:" << e.what() << "\n";

                // If loading the SV6 or SV4 failed return to the title screen if requested.
                if (loadTitleScreenFirstOnFail)
                {
                    SetActiveScene(GetTitleScene());
                }
                // The path needs to be duplicated as it's a const here
                // which the window function doesn't like
                auto intent = Intent(WindowClass::ObjectLoadError);
                intent.PutExtra(INTENT_EXTRA_PATH, path);
                intent.PutExtra(INTENT_EXTRA_LIST, const_cast<ObjectEntryDescriptor*>(e.MissingObjects.data()));
                intent.PutExtra(INTENT_EXTRA_LIST_COUNT, static_cast<uint32_t>(e.MissingObjects.size()));

                auto windowManager = _uiContext->GetWindowManager();
                windowManager->OpenIntent(&intent);

				{
                    const std::string error{e.what()};
                    VerboseSend(socket, portAddress2, error);
                }
                 //std::cout<<"sent error\n";

             }
             catch (const UnsupportedRideTypeException& e)
             {
                Console::Error::WriteLine("Unable to open park: unsupported ride types");
				std::cout <<" error loading C:" << e.what() << "\n";

                // If loading the SV6 or SV4 failed return to the title screen if requested.
                if (loadTitleScreenFirstOnFail)
                {
                    SetActiveScene(GetTitleScene());
                }
                auto windowManager = _uiContext->GetWindowManager();
                windowManager->ShowError(STR_FILE_CONTAINS_UNSUPPORTED_RIDE_TYPES, kStringIdNone, {});

                {
                    const std::string error{e.what()};
                    VerboseSend(socket, portAddress2, error);
                }
             }
             catch (const UnsupportedVersionException& e)
             {
                Console::Error::WriteLine("Unable to open park: unsupported park version");
				std::cout <<" error loading B:" << e.what() << "\n";

                if (loadTitleScreenFirstOnFail)
                {
                    SetActiveScene(GetTitleScene());
                }
                auto windowManager = _uiContext->GetWindowManager();
                Formatter ft;
                /*if (e.TargetVersion < kParkFileMinSupportedVersion)
                {
                    ft.Add<uint32_t>(e.TargetVersion);
                    windowManager->ShowError(STR_ERROR_PARK_VERSION_TITLE, STR_ERROR_PARK_VERSION_TOO_OLD_MESSAGE, ft);
                }
                else*/
                {
                    if (e.MinVersion == e.TargetVersion)
                     {
                         ft.Add<uint32_t>(e.TargetVersion);
                         ft.Add<uint32_t>(OpenRCT2::kParkFileCurrentVersion);
                         windowManager->ShowError(STR_ERROR_PARK_VERSION_TITLE, STR_ERROR_PARK_VERSION_TOO_NEW_MESSAGE_2, ft);
                     }
                     else
                     {
                         ft.Add<uint32_t>(e.TargetVersion);
                         ft.Add<uint32_t>(e.MinVersion);
                         ft.Add<uint32_t>(OpenRCT2::kParkFileCurrentVersion);
                         windowManager->ShowError(STR_ERROR_PARK_VERSION_TITLE, STR_ERROR_PARK_VERSION_TOO_NEW_MESSAGE, ft);
                     }
                 }

                 {
                     const std::string error{e.what()};
                     VerboseSend(socket, portAddress2, error);
                 }

             }
             /*catch (const std::exception& e)
             {
				std::cout <<" error loading A:" << e.what() << "\n";

                // If loading the SV6 or SV4 failed return to the title screen if requested.
                if (loadTitleScreenFirstOnFail)
                {
                    SetActiveScene(GetTitleScene());
                }
                Console::Error::WriteLine(e.what());
				
				{
                    const std::string error{e.what()};
                    VerboseSend(socket, portAddress2, error);
                }
             }*/

            CloseProgress();
            WindowSetFlagForAllViewports(VIEWPORT_FLAG_RENDERING_INHIBITED, false);
            return false;
        }

    private:
        bool HasObjectsThatUseFallbackImages()
        {
            for (auto objectType : getAllObjectTypes())
            {
                auto maxObjectsOfType = static_cast<ObjectEntryIndex>(getObjectEntryGroupCount(objectType));
                for (ObjectEntryIndex i = 0; i < maxObjectsOfType; i++)
                {
                    auto obj = _objectManager->GetLoadedObject(objectType, i);
                    if (obj != nullptr)
                    {
                        if (obj->UsesFallbackImages())
                            return true;
                    }
                }
            }
            return false;
        }

        std::string GetOrPromptRCT2Path()
        {
            auto result = std::string();
            if (gCustomRCT2DataPath.empty())
            {
                // Check install directory
                if (Config::Get().general.RCT2Path.empty() || !Platform::OriginalGameDataExists(Config::Get().general.RCT2Path))
                {
                    LOG_VERBOSE(
                        "install directory does not exist or invalid directory selected, %s",
                        Config::Get().general.RCT2Path.c_str());
                    if (!Config::FindOrBrowseInstallDirectory())
                    {
                        auto path = Config::GetDefaultPath();
                        Console::Error::WriteLine(
                            "An RCT2 install directory must be specified! Please edit \"game_path\" in %s.\n", path.c_str());
                        return std::string();
                    }
                }
                result = Config::Get().general.RCT2Path;
            }
            else
            {
                result = gCustomRCT2DataPath;
            }
            return result;
        }

        // TODO: move function elsewhere?
        bool LoadBaseGraphics()
        {
            if (!GfxLoadG1(*_env))
            {
                return false;
            }
            GfxLoadG2();
            GfxLoadCsg();
            FontSpriteInitialiseCharacters();
            return true;
        }

        void SwitchToStartUpScene()
        {
            if (gOpenRCT2Headless)
            {
                // NONE or OPEN are the only allowed actions for headless mode
                if (gOpenRCT2StartupAction != StartupAction::Open)
                {
                    gOpenRCT2StartupAction = StartupAction::None;
                }
            }
            else
            {
                if ((gOpenRCT2StartupAction == StartupAction::Title) && Config::Get().general.PlayIntro)
                {
                    gOpenRCT2StartupAction = StartupAction::Intro;
                }
            }

            IScene* nextScene{};
            switch (gOpenRCT2StartupAction)
            {
                case StartupAction::Intro:
                {
                    nextScene = GetIntroScene();
                    break;
                }

                case StartupAction::Title:
                {
                    nextScene = GetTitleScene();
                    break;
                }

                case StartupAction::Open:
                {
                    // A path that includes "://" is illegal with all common filesystems, so it is almost certainly a URL
                    // This way all cURL supported protocols, like http, ftp, scp and smb are automatically handled
                    if (strstr(gOpenRCT2StartupActionPath, "://") != nullptr)
                    {
#ifndef DISABLE_HTTP
                        // Download park and open it using its temporary filename
                        auto data = DownloadPark(gOpenRCT2StartupActionPath);
                        if (data.empty())
                        {
                            nextScene = GetTitleScene();
                            break;
                        }

                        auto ms = MemoryStream(data.data(), data.size(), MEMORY_ACCESS::READ);
                        if (!LoadParkFromStream(&ms, gOpenRCT2StartupActionPath, true))
                        {
                            Console::Error::WriteLine("Failed to load '%s'", gOpenRCT2StartupActionPath);
                            nextScene = GetTitleScene();
                            break;
                        }
#endif
                    }
                    else
                    {
                       // try
                        {
                            if (!LoadParkFromFile(gOpenRCT2StartupActionPath, true, true, false))
                            {
								std::cout<<" couldn't load file\n";
                                nextScene = GetTitleScene();
                                break;
                            }
                        }
                        /*catch (const std::exception& ex)
                        {
                            Console::Error::WriteLine("Failed to load '%s'", gOpenRCT2StartupActionPath);
                            Console::Error::WriteLine("%s", ex.what());
							std::cout<<"error: " << ex.what()<< "\n";
                            nextScene = GetTitleScene();
                            break;
                        }*/
                    }

                    // Successfully loaded a file
                    nextScene = GetGameScene();
                    break;
                }

                case StartupAction::Edit:
                {
                    if (String::sizeOf(gOpenRCT2StartupActionPath) == 0)
                    {
                        Editor::Load();
                        nextScene = GetGameScene();
                    }
                    else if (Editor::LoadLandscape(gOpenRCT2StartupActionPath))
                    {
                        nextScene = GetGameScene();
                    }
                    else
                    {
                        nextScene = GetTitleScene();
                    }
                    break;
                }

                default:
                {
                    nextScene = GetTitleScene();
                }
            }

            SetActiveScene(nextScene);
            InitNetworkGame(nextScene == GetGameScene());
        }

        void InitNetworkGame(bool isGameScene)
        {
			std::cout<<"\n\ninit network game\n\n";
            if (isGameScene)
            {
#ifndef DISABLE_NETWORK
                if (gNetworkStart == NETWORK_MODE_SERVER)
                {
                    if (gNetworkStartPort == 0)
                    {
                        gNetworkStartPort = Config::Get().network.DefaultPort;
                    }

                    if (gNetworkStartAddress.empty())
                    {
                        gNetworkStartAddress = Config::Get().network.ListenAddress;
                    }

                    if (gCustomPassword.empty())
                    {
                        _network.SetPassword(Config::Get().network.DefaultPassword.c_str());
                    }
                    else
                    {
                        _network.SetPassword(gCustomPassword);
                    }
                    _network.BeginServer(gNetworkStartPort, gNetworkStartAddress);
                }
                else
#endif // DISABLE_NETWORK
                {
                    GameLoadScripts();
                    GameNotifyMapChanged();
                }
            }

#ifndef DISABLE_NETWORK
            else if (gNetworkStart == NETWORK_MODE_CLIENT)
            {
                if (gNetworkStartPort == 0)
                {
                    gNetworkStartPort = Config::Get().network.DefaultPort;
                }
                _network.BeginClient(gNetworkStartHost, gNetworkStartPort);
            }
#endif // DISABLE_NETWORK
        }

        /**
         * Launches the game, after command line arguments have been parsed and processed.
         */
        void Launch()
        {
            if (!_versionCheckFuture.valid())
            {
                _versionCheckFuture = std::async(std::launch::async, [this] {
                    _newVersionInfo = GetLatestVersion();
                    if (!String::startsWith(gVersionInfoTag, _newVersionInfo.tag))
                    {
                        _hasNewVersionInfo = true;
                    }
                });
            }

            if (!gOpenRCT2Headless)
            {
                _preloaderScene->SetOnComplete([&]() { SwitchToStartUpScene(); });
            }
            else
            {
                SwitchToStartUpScene();
            }
#ifdef __EMSCRIPTEN__
            emscripten_set_main_loop_arg(
                [](void* vctx) {
                    auto ctx = reinterpret_cast<Context*>(vctx);
                    if (ctx->_finished)
                    {
                        emscripten_cancel_main_loop();
                    }
                    ctx->RunFrame();
                },
                this, 0, 1);
#else
            _stdInOutConsole.Start();
            RunGameLoop();
#endif
        }

        bool ShouldDraw()
        {
            if (gOpenRCT2Headless)
                return false;
            if (_uiContext->IsMinimised())
                return false;
            return true;
        }

        bool ShouldRunVariableFrame()
        {
            if (!ShouldDraw())
                return false;
            if (!Config::Get().general.UncapFPS)
                return false;
            if (gGameSpeed > 4)
                return false;
            return true;
        }

        /**
         * Run the main game loop until the finished flag is set.
         */
#ifndef __EMSCRIPTEN__
        void RunGameLoop()
        {
            PROFILED_FUNCTION();

            LOG_VERBOSE("begin openrct2 loop");
            _finished = false;

            _variableFrame = ShouldRunVariableFrame();
            do
            {
                RunFrame();
            } while (!_finished);
            LOG_VERBOSE("finish openrct2 loop");
        }
#endif // __EMSCRIPTEN__

        void RunFrame()
        {
            PROFILED_FUNCTION();

            const auto deltaTime = _timer.GetElapsedTimeAndRestart().count();

            // Make sure we catch the state change and reset it.
            bool useVariableFrame = ShouldRunVariableFrame();
            if (_variableFrame != useVariableFrame)
            {
                _variableFrame = useVariableFrame;

                // Switching from variable to fixed frame requires reseting
                // of entity positions back to end of tick positions
                auto& tweener = EntityTweener::Get();
                tweener.Restore();
                tweener.Reset();
            }

            UpdateTimeAccumulators(deltaTime);

            if (useVariableFrame)
            {
                RunVariableFrame(deltaTime);
            }
            else
            {
                RunFixedFrame(deltaTime);
            }
        }

        void UpdateTimeAccumulators(float deltaTime)
        {
            // Ticks
            float scaledDeltaTime = deltaTime * _timeScale;
            _ticksAccumulator = std::min(_ticksAccumulator + scaledDeltaTime, kGameUpdateMaxThreshold);

            // Real Time.
            _realtimeAccumulator = std::min(_realtimeAccumulator + deltaTime, kGameUpdateMaxThreshold);
            while (_realtimeAccumulator >= kGameUpdateTimeMS)
            {
                gCurrentRealTimeTicks++;
                _realtimeAccumulator -= kGameUpdateTimeMS;
            }
        }

        void RunFixedFrame(float deltaTime)
        {
            PROFILED_FUNCTION();

            _uiContext->ProcessMessages();

            if (_ticksAccumulator < kGameUpdateTimeMS)
            {
                const auto sleepTimeSec = (kGameUpdateTimeMS - _ticksAccumulator);
                Platform::Sleep(static_cast<uint32_t>(sleepTimeSec * 1000.f));
                return;
            }

            while (_ticksAccumulator >= kGameUpdateTimeMS)
            {
                Tick();

                _ticksAccumulator -= kGameUpdateTimeMS;
            }

            _backgroundWorker.dispatchCompleted();

            ContextHandleInput();
            WindowUpdateAll();

            if (ShouldDraw())
            {
                Draw();
            }
        }

        void RunVariableFrame(float deltaTime)
        {
            PROFILED_FUNCTION();

            const bool shouldDraw = ShouldDraw();
            auto& tweener = EntityTweener::Get();

            _uiContext->ProcessMessages();

            while (_ticksAccumulator >= kGameUpdateTimeMS)
            {
                // Get the original position of each sprite
                if (shouldDraw)
                    tweener.PreTick();

                Tick();

                _ticksAccumulator -= kGameUpdateTimeMS;

                // Get the next position of each sprite
                if (shouldDraw)
                    tweener.PostTick();
            }

            _backgroundWorker.dispatchCompleted();

            ContextHandleInput();
            WindowUpdateAll();

            if (shouldDraw)
            {
                const float alpha = std::min(_ticksAccumulator / kGameUpdateTimeMS, 1.0f);
                tweener.Tween(alpha);

                Draw();
            }
        }

        void Draw()
        {
            PROFILED_FUNCTION();

            _drawingEngine->BeginDraw();
            _painter->Paint(*_drawingEngine);
            _drawingEngine->EndDraw();
        }

        void Tick()
        {
            PROFILED_FUNCTION();

            // TODO: This variable has been never "variable" in time, some code expects
            // this to be 40Hz (25 ms). Refactor this once the UI is decoupled.
            gCurrentDeltaTime = static_cast<uint16_t>(kGameUpdateTimeMS * 1000.0f);

            if (GameIsNotPaused())
            {
                gPaletteEffectFrame += gCurrentDeltaTime;
            }

            DateUpdateRealTimeOfDay();

            if (_activeScene)
                _activeScene->Tick();

#ifdef __ENABLE_DISCORD__
            if (_discordService != nullptr)
            {
                _discordService->Tick();
            }
#endif

            ChatUpdate();
#ifdef ENABLE_SCRIPTING
            if (GetActiveScene() != GetPreloaderScene())
            {
                _scriptEngine.Tick();
            }
#endif
            _stdInOutConsole.ProcessEvalQueue();
            _uiContext->Tick();
        }

        /**
         * Ensure that the custom user content folders are present
         */
        void EnsureUserContentDirectoriesExist()
        {
            EnsureDirectoriesExist(
                DirBase::user,
                {
                    DirId::objects,
                    DirId::saves,
                    DirId::scenarios,
                    DirId::trackDesigns,
                    DirId::landscapes,
                    DirId::heightmaps,
                    DirId::plugins,
                    DirId::themes,
                    DirId::sequences,
                    DirId::replayRecordings,
                    DirId::desyncLogs,
                    DirId::crashDumps,
                });
        }

        void EnsureDirectoriesExist(const DirBase dirBase, const std::initializer_list<DirId>& dirIds)
        {
            for (const auto& dirId : dirIds)
            {
                auto path = _env->GetDirectoryPath(dirBase, dirId);
                if (!Path::CreateDirectory(path))
                    LOG_ERROR("Unable to create directory '%s'.", path.c_str());
            }
        }

        /**
         * Copy saved games and landscapes to user directory
         */
        void CopyOriginalUserFilesOver()
        {
            CopyOriginalUserFilesOver(DirId::saves, "*.sv6");
            CopyOriginalUserFilesOver(DirId::landscapes, "*.sc6");
        }

        void CopyOriginalUserFilesOver(DirId dirid, const std::string& pattern)
        {
            auto src = _env->GetDirectoryPath(DirBase::rct2, dirid);
            auto dst = _env->GetDirectoryPath(DirBase::user, dirid);
            CopyOriginalUserFilesOver(src, dst, pattern);
        }

        void CopyOriginalUserFilesOver(const std::string& srcRoot, const std::string& dstRoot, const std::string& pattern)
        {
            LOG_VERBOSE("CopyOriginalUserFilesOver('%s', '%s', '%s')", srcRoot.c_str(), dstRoot.c_str(), pattern.c_str());

            auto scanPattern = Path::Combine(srcRoot, pattern);
            auto scanner = Path::ScanDirectory(scanPattern, true);
            while (scanner->Next())
            {
                auto src = std::string(scanner->GetPath());
                auto dst = Path::Combine(dstRoot, scanner->GetPathRelative());
                auto dstDirectory = Path::GetDirectory(dst);

                // Create the directory if necessary
                if (!Path::CreateDirectory(dstDirectory))
                {
                    Console::Error::WriteLine("Could not create directory %s.", dstDirectory.c_str());
                    break;
                }

                // Only copy the file if it doesn't already exist
                if (!File::Exists(dst))
                {
                    Console::WriteLine("Copying '%s' to '%s'", src.c_str(), dst.c_str());
                    if (!File::Copy(src, dst, false))
                    {
                        Console::Error::WriteLine("Failed to copy '%s' to '%s'", src.c_str(), dst.c_str());
                    }
                }
            }
        }

#ifndef DISABLE_HTTP
        std::vector<uint8_t> DownloadPark(const std::string& url)
        {
            // Download park to buffer in memory
            Http::Request request;
            request.url = url;
            request.method = Http::Method::GET;

            Http::Response res;
            try
            {
                res = Do(request);
                if (res.status != Http::Status::Ok)
                    throw std::runtime_error("bad http status");
            }
            catch (std::exception& e)
            {
                Console::Error::WriteLine("Failed to download '%s', cause %s", request.url.c_str(), e.what());
                return {};
            }

            std::vector<uint8_t> parkData;
            parkData.resize(res.body.size());
            std::memcpy(parkData.data(), res.body.c_str(), parkData.size());
            return parkData;
        }
#endif

        bool HasNewVersionInfo() const override
        {
            return _hasNewVersionInfo;
        }

        const NewVersionInfo* GetNewVersionInfo() const override
        {
            return &_newVersionInfo;
        }

        void SetTimeScale(float newScale) override
        {
            _timeScale = std::clamp(newScale, kGameMinTimeScale, kGameMaxTimeScale);
        }

        float GetTimeScale() const override
        {
            return _timeScale;
        }

        BackgroundWorker& GetBackgroundWorker() override
        {
            return _backgroundWorker;
        }
    };

    Context* Context::Instance = nullptr;

    std::unique_ptr<IContext> CreateContext()
    {
        return CreateContext(CreatePlatformEnvironment(), Audio::CreateDummyAudioContext(), CreateDummyUiContext());
    }

    std::unique_ptr<IContext> CreateContext(
        const std::shared_ptr<IPlatformEnvironment>& env, const std::shared_ptr<Audio::IAudioContext>& audioContext,
        const std::shared_ptr<IUiContext>& uiContext)
    {
        return std::make_unique<Context>(env, audioContext, uiContext);
    }

    IContext* GetContext()
    {
        return Context::Instance;
    }

} // namespace OpenRCT2

void ContextInit()
{
    GetWindowManager()->Init();
}

bool ContextLoadParkFromStream(void* stream)
{
    return GetContext()->LoadParkFromStream(static_cast<IStream*>(stream), "");
}

void OpenRCT2Finish()
{
    GetContext()->Finish();
}

void ContextSetCurrentCursor(CursorID cursor)
{
    GetContext()->GetUiContext()->SetCursor(cursor);
}

void ContextUpdateCursorScale()
{
    GetContext()->GetUiContext()->SetCursorScale(static_cast<uint8_t>(std::round(Config::Get().general.WindowScale)));
}

void ContextHideCursor()
{
    GetContext()->GetUiContext()->SetCursorVisible(false);
}

void ContextShowCursor()
{
    GetContext()->GetUiContext()->SetCursorVisible(true);
}

ScreenCoordsXY ContextGetCursorPosition()
{
    return GetContext()->GetUiContext()->GetCursorPosition();
}

ScreenCoordsXY ContextGetCursorPositionScaled()
{
    auto cursorCoords = ContextGetCursorPosition();
    // Compensate for window scaling.
    return { static_cast<int32_t>(std::ceil(cursorCoords.x / Config::Get().general.WindowScale)),
             static_cast<int32_t>(std::ceil(cursorCoords.y / Config::Get().general.WindowScale)) };
}

void ContextSetCursorPosition(const ScreenCoordsXY& cursorPosition)
{
    GetContext()->GetUiContext()->SetCursorPosition(cursorPosition);
}

const CursorState* ContextGetCursorState()
{
    return GetContext()->GetUiContext()->GetCursorState();
}

const uint8_t* ContextGetKeysState()
{
    return GetContext()->GetUiContext()->GetKeysState();
}

const uint8_t* ContextGetKeysPressed()
{
    return GetContext()->GetUiContext()->GetKeysPressed();
}

TextInputSession* ContextStartTextInput(u8string& buffer, size_t maxLength)
{
    return GetContext()->GetUiContext()->StartTextInput(buffer, maxLength);
}

void ContextStopTextInput()
{
    GetContext()->GetUiContext()->StopTextInput();
}

bool ContextIsInputActive()
{
    return GetContext()->GetUiContext()->IsTextInputActive();
}

void ContextTriggerResize()
{
    return GetContext()->GetUiContext()->TriggerResize();
}

void ContextSetFullscreenMode(int32_t mode)
{
    return GetContext()->GetUiContext()->SetFullscreenMode(static_cast<FullscreenMode>(mode));
}

void ContextRecreateWindow()
{
    GetContext()->GetUiContext()->RecreateWindow();
}

int32_t ContextGetWidth()
{
    return GetContext()->GetUiContext()->GetWidth();
}

int32_t ContextGetHeight()
{
    return GetContext()->GetUiContext()->GetHeight();
}

bool ContextHasFocus()
{
    return GetContext()->GetUiContext()->HasFocus();
}

void ContextSetCursorTrap(bool value)
{
    GetContext()->GetUiContext()->SetCursorTrap(value);
}

WindowBase* ContextOpenWindow(WindowClass wc)
{
    auto windowManager = Ui::GetWindowManager();
    return windowManager->OpenWindow(wc);
}

WindowBase* ContextOpenWindowView(uint8_t wc)
{
    auto windowManager = Ui::GetWindowManager();
    return windowManager->OpenView(wc);
}

WindowBase* ContextOpenDetailWindow(uint8_t type, int32_t id)
{
    auto windowManager = Ui::GetWindowManager();
    return windowManager->OpenDetails(type, id);
}

WindowBase* ContextOpenIntent(Intent* intent)
{
    auto windowManager = Ui::GetWindowManager();
    return windowManager->OpenIntent(intent);
}

void ContextBroadcastIntent(Intent* intent)
{
    auto windowManager = Ui::GetWindowManager();
    windowManager->BroadcastIntent(*intent);
}

void ContextForceCloseWindowByClass(WindowClass windowClass)
{
    auto windowManager = Ui::GetWindowManager();
    windowManager->ForceClose(windowClass);
}

WindowBase* ContextShowError(StringId title, StringId message, const Formatter& args, const bool autoClose /* = false */)
{
    auto windowManager = Ui::GetWindowManager();
    return windowManager->ShowError(title, message, args, autoClose);
}

void ContextHandleInput()
{
    auto windowManager = Ui::GetWindowManager();
    windowManager->HandleInput();
}

void ContextInputHandleKeyboard(bool isTitle)
{
    auto windowManager = Ui::GetWindowManager();
    windowManager->HandleKeyboard(isTitle);
}

void ContextQuit()
{
    GetContext()->Quit();
}

u8string ContextOpenCommonFileDialog(OpenRCT2::Ui::FileDialogDesc& desc)
{
    try
    {
        return GetContext()->GetUiContext()->ShowFileDialog(desc);
    }
    catch (const std::exception& ex)
    {
        LOG_ERROR(ex.what());
        return u8string{};
    }
}
