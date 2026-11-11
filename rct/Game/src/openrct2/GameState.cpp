#include "zmq.hpp"

#include "GameState.h"
#include "ride/TrackDesignRepository.h"
#include "actions/ClearAction.h"
#include "actions/TrackDesignAction.h"
#include "actions/RideSetStatusAction.h"
#include "actions/RideDemolishAction.h"

#include "world/tile_element/SurfaceElement.h"
#include "world/tile_element/PathElement.h"
#include "world/tile_element/TrackElement.h"
#include "world/tile_element/WallElement.h"
#include "world/tile_element/SmallSceneryElement.h"
#include "world/tile_element/LargeSceneryElement.h"
#include "world/tile_element/EntranceElement.h"
#include "ride/RideManager.hpp"
#include "ui/WindowManager.h"
#include "entity/EntityList.h"
#include "ride/RideTypes.h"
#include "object/ObjectLimits.h"
#include "world/Wall.h"
#include "ride/RideConstruction.h"

#include "world/Footpath.h"
#include "world/tile_element/Slope.h"
#include "actions/FootpathPlaceAction.h"
#include "actions/ParkSetParameterAction.h"
#include "actions/RideCreateAction.h"
#include "ride/RideConstruction.h"
#include "actions/TrackPlaceAction.h"
#include "actions/RideEntranceExitPlaceAction.h"
#include "ride/RideData.h"
#include "ride/Ride.h"
#include "actions/RideSetSettingAction.h"
#include "Cheats.h"
#include "actions/RideSetPriceAction.h"
#include "object/ObjectManager.h"
#include "actions/ParkSetEntranceFeeAction.h"
#include "localisation/Formatting.h"
#include "object/ObjectRepository.h"
#include "ride/TrackData.h"

#include "json/json.h"

using namespace std::chrono_literals;

// initialize the zmq context with a single IO thread
static zmq::context_t context_gs{1};

// construct a REP (reply) socket and bind to interface
static zmq::socket_t socket_gs{context_gs, zmq::socket_type::router};
static bool firstRun = true;
static int32_t num_ticks = -1;
static int32_t current_month = -1;

static zmq::socket_t socket_send{context_gs, zmq::socket_type::dealer};

static std::string portAddress1;
std::string portAddress2;

static int** visitCounts;

/*****************************************************************************
 * Copyright (c) 2014-2025 OpenRCT2 developers
 *
 * For a complete list of all authors, please refer to contributors.md
 * Interested in contributing? Visit https://github.com/OpenRCT2/OpenRCT2
 *
 * OpenRCT2 is licensed under the GNU General Public License version 3.
 *****************************************************************************/

#include "GameState.h"

#include "Game.h"
#include "GameStateSnapshots.h"
#include "Input.h"
#include "OpenRCT2.h"
#include "ReplayManager.h"
#include "actions/GameAction.h"
#include "config/Config.h"
#include "entity/EntityTweener.h"
#include "entity/PatrolArea.h"
#include "interface/Screenshot.h"
#include "platform/Platform.h"
#include "profiling/Profiling.h"
#include "ride/Vehicle.h"
#include "scenes/title/TitleScene.h"
#include "scenes/title/TitleSequencePlayer.h"
#include "scripting/ScriptEngine.h"
#include "ui/UiContext.h"
#include "windows/Intent.h"
#include "world/MapAnimation.h"
#include "world/Scenery.h"

using namespace OpenRCT2::Scripting;

static constexpr ride_type_t RideTypeViewOrder2[] = {
    // Transport rides
    RIDE_TYPE_MINIATURE_RAILWAY,
    RIDE_TYPE_MONORAIL,
    RIDE_TYPE_SUSPENDED_MONORAIL,
    RIDE_TYPE_CHAIRLIFT,
    RIDE_TYPE_LIFT,

    // Roller Coasters
    RIDE_TYPE_SIDE_FRICTION_ROLLER_COASTER,
    RIDE_TYPE_VIRGINIA_REEL,
    RIDE_TYPE_REVERSER_ROLLER_COASTER,
    RIDE_TYPE_CLASSIC_WOODEN_ROLLER_COASTER,
    RIDE_TYPE_WOODEN_ROLLER_COASTER,
    RIDE_TYPE_WOODEN_WILD_MOUSE,
    RIDE_TYPE_STEEL_WILD_MOUSE,
    RIDE_TYPE_SPINNING_WILD_MOUSE,
    RIDE_TYPE_INVERTED_HAIRPIN_COASTER,
    RIDE_TYPE_JUNIOR_ROLLER_COASTER,
    RIDE_TYPE_CLASSIC_MINI_ROLLER_COASTER,
    RIDE_TYPE_MINI_ROLLER_COASTER,
    RIDE_TYPE_SPIRAL_ROLLER_COASTER,
    RIDE_TYPE_MINE_TRAIN_COASTER,
    RIDE_TYPE_LOOPING_ROLLER_COASTER,
    RIDE_TYPE_STAND_UP_ROLLER_COASTER,
    RIDE_TYPE_CLASSIC_STAND_UP_ROLLER_COASTER,
    RIDE_TYPE_CORKSCREW_ROLLER_COASTER,
    RIDE_TYPE_HYPERCOASTER,
    RIDE_TYPE_LIM_LAUNCHED_ROLLER_COASTER,
    RIDE_TYPE_TWISTER_ROLLER_COASTER,
    RIDE_TYPE_HYPER_TWISTER,
    RIDE_TYPE_GIGA_COASTER,
    RIDE_TYPE_SUSPENDED_SWINGING_COASTER,
    RIDE_TYPE_COMPACT_INVERTED_COASTER,
    RIDE_TYPE_INVERTED_ROLLER_COASTER,
    RIDE_TYPE_INVERTED_IMPULSE_COASTER,
    RIDE_TYPE_MINI_SUSPENDED_COASTER,
    RIDE_TYPE_STEEPLECHASE,
    RIDE_TYPE_BOBSLEIGH_COASTER,
    RIDE_TYPE_MINE_RIDE,
    RIDE_TYPE_HEARTLINE_TWISTER_COASTER,
    RIDE_TYPE_LAY_DOWN_ROLLER_COASTER,
    RIDE_TYPE_FLYING_ROLLER_COASTER,
    RIDE_TYPE_MULTI_DIMENSION_ROLLER_COASTER,
    RIDE_TYPE_REVERSE_FREEFALL_COASTER,
    RIDE_TYPE_VERTICAL_DROP_ROLLER_COASTER,
    RIDE_TYPE_AIR_POWERED_VERTICAL_COASTER,
    RIDE_TYPE_HYBRID_COASTER,
    RIDE_TYPE_SINGLE_RAIL_ROLLER_COASTER,
    RIDE_TYPE_ALPINE_COASTER,

    // Gentle rides
    RIDE_TYPE_MONORAIL_CYCLES,
    RIDE_TYPE_CROOKED_HOUSE,
    RIDE_TYPE_HAUNTED_HOUSE,
    RIDE_TYPE_FERRIS_WHEEL,
    RIDE_TYPE_MAZE,
    RIDE_TYPE_MERRY_GO_ROUND,
    RIDE_TYPE_MINI_GOLF,
    RIDE_TYPE_OBSERVATION_TOWER,
    RIDE_TYPE_CAR_RIDE,
    RIDE_TYPE_MONSTER_TRUCKS,
    RIDE_TYPE_MINI_HELICOPTERS,
    RIDE_TYPE_SPIRAL_SLIDE,
    RIDE_TYPE_DODGEMS,
    RIDE_TYPE_SPACE_RINGS,
    RIDE_TYPE_CIRCUS,
    RIDE_TYPE_GHOST_TRAIN,
    RIDE_TYPE_FLYING_SAUCERS,

    // Thrill rides
    RIDE_TYPE_TWIST,
    RIDE_TYPE_MAGIC_CARPET,
    RIDE_TYPE_LAUNCHED_FREEFALL,
    RIDE_TYPE_SWINGING_SHIP,
    RIDE_TYPE_GO_KARTS,
    RIDE_TYPE_SWINGING_INVERTER_SHIP,
    RIDE_TYPE_MOTION_SIMULATOR,
    RIDE_TYPE_3D_CINEMA,
    RIDE_TYPE_TOP_SPIN,
    RIDE_TYPE_ROTO_DROP,
    RIDE_TYPE_ENTERPRISE,

    // Water rides
    RIDE_TYPE_DINGHY_SLIDE,
    RIDE_TYPE_LOG_FLUME,
    RIDE_TYPE_RIVER_RAPIDS,
    RIDE_TYPE_SPLASH_BOATS,
    RIDE_TYPE_SUBMARINE_RIDE,
    RIDE_TYPE_BOAT_HIRE,
    RIDE_TYPE_RIVER_RAFTS,
    RIDE_TYPE_WATER_COASTER,

    // Shops / stalls
    RIDE_TYPE_FOOD_STALL,
    RIDE_TYPE_1D,
    RIDE_TYPE_DRINK_STALL,
    RIDE_TYPE_1F,
    RIDE_TYPE_SHOP,
    RIDE_TYPE_22,
    RIDE_TYPE_INFORMATION_KIOSK,
    RIDE_TYPE_FIRST_AID,
    RIDE_TYPE_CASH_MACHINE,
    RIDE_TYPE_TOILETS,
};

namespace OpenRCT2
{
    static auto _gameState = std::make_unique<GameState_t>();

    GameState_t& getGameState()
    {
        return *_gameState;
    }

    void swapGameState(std::unique_ptr<GameState_t>& otherState)
    {
        _gameState.swap(otherState);
    }

    /**
     * Initialises the map, park etc. basically all S6 data.
     */
    void gameStateInitAll(GameState_t& gameState, const TileCoordsXY& mapSize)
    {
        PROFILED_FUNCTION();

        gInMapInitCode = true;
        gameState.currentTicks = 0;

        MapInit(mapSize);
        Park::Initialise(gameState);
        FinanceInit();
        BannerInit(gameState);
        RideInitAll();
        ResetAllEntities();
        UpdateConsolidatedPatrolAreas();
        ResetDate();
        ClimateReset();
        News::InitQueue(gameState);

        gInMapInitCode = false;

        gameState.nextGuestNumber = 1;

        ContextInit();

        auto sceneryIntent = Intent(INTENT_ACTION_SET_DEFAULT_SCENERY_CONFIG);
        ContextBroadcastIntent(&sceneryIntent);

        auto clipboardIntent = Intent(INTENT_ACTION_CLEAR_TILE_INSPECTOR_CLIPBOARD);
        ContextBroadcastIntent(&clipboardIntent);

        LoadPalette();

        CheatsReset();
        ClearRestrictedScenery();

#ifdef ENABLE_SCRIPTING
        auto& scriptEngine = GetContext()->GetScriptEngine();
        scriptEngine.ClearParkStorage();
#endif

        EntityTweener::Get().Reset();
		
		if (firstRun) //socket_gs.handle() == nullptr)
		{
			std::cout<< "FIRSTRUN\n";
			
			firstRun = false;
			int port = gNetworkStartPort;
			if (port == 0) {
				port = Config::Get().network.DefaultPort;
			}
			portAddress1 = "tcp://*:" + std::to_string(port);
			portAddress2 = "tcp://localhost:" + std::to_string(port+1);
			std::cout<<"GS BIND: " << portAddress1 << " and " << portAddress2 << "\n";
		    socket_gs.bind(portAddress1.c_str());
			CheatsSet(CheatType::BuildInPauseMode, true);
		}
    }

	static RideId createdRideID = RideId::GetNull();

    /**
     * Function will be called every kGameUpdateTimeMS.
     * It has its own loop which might run multiple updates per call such as
     * when operating as a client it may run multiple updates to catch up with the server tick,
     * another influence can be the game speed setting.
     */
    void gameStateTick()
    {
        PROFILED_FUNCTION();

        // Normal game play will update only once every kGameUpdateTimeMS
        uint32_t numUpdates = 1;

        // 0x006E3AEC // screen_game_process_mouse_input();
        ScreenshotCheck();
        GameHandleKeyboardInput();

        if (GameIsNotPaused() && gPreviewingTitleSequenceInGame)
        {
            auto player = GetContext()->GetUiContext()->GetTitleSequencePlayer();
            if (player != nullptr)
            {
                player->Update();
            }
        }

        NetworkUpdate();

        if (NetworkGetMode() == NETWORK_MODE_CLIENT && NetworkGetStatus() == NETWORK_STATUS_CONNECTED
            && NetworkGetAuthstatus() == NetworkAuth::Ok)
        {
            numUpdates = std::clamp<uint32_t>(NetworkGetServerTick() - getGameState().currentTicks, 0, 10);
        }
        else
        {
            // Determine how many times we need to update the game
            if (gGameSpeed > 1)
            {
                // Update more often if game speed is above normal.
                numUpdates = 1 << (gGameSpeed - 1);
            }
        }

        bool isPaused = GameIsPaused();
        if (NetworkGetMode() == NETWORK_MODE_SERVER && Config::Get().network.PauseServerIfNoClients)
        {
            // If we are headless we always have 1 player (host), pause if no one else is around.
            if (gOpenRCT2Headless && NetworkGetNumPlayers() == 1)
            {
                isPaused |= true;
            }
        }

	    auto& gameState = OpenRCT2::getGameState();

        bool didRunSingleFrame = false;
        if (isPaused)
        {
            auto* windowMgr = Ui::GetWindowManager();
            windowMgr->CloseAll();
			
		    zmq::message_t request;
		    auto num = socket_gs.recv(request, zmq::recv_flags::dontwait);
			if (num > 0)
			{
				Json::Value res;
				Json::Reader reader = {};
				auto status = reader.parse(request.to_string(), res);
		        if (!status) {
		        } else {
					//WindowCloseAll();
					if (res["action"] == "unpause")
					{
						//std::cout<<"unpause\n";
						gGamePaused = false;
						isPaused = false;
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer("done"), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "load_park")
					{
						std::string path = res["path"].asString();
						//const char* path_c = path.c_str();
						//std::cout<<"loading\n";
						std::cout<<"Loading(a) " << path<< "\n";
					    OpenRCT2::GetContext()->LoadParkFromFile(path, false, true);
						//gGamePaused = true;
					
						// set loan to maximum
						//gameState.maxBankLoan = 1000000;
						/*if (gameState.bankLoan < gameState.maxBankLoan)
						{
							auto diff = gameState.maxBankLoan - gameState.bankLoan;
							gameState.bankLoan = gameState.maxBankLoan;
							gameState.cash += diff;
						}*/
					
						/*auto currentCash = FinanceGetCurrentCash();
						if (currentCash < 200000)
						{
							gameState.bankLoan += (200000-currentCash);
							gameState.cash += (200000-currentCash);
						}*/
						gGamePaused = true;
					}
					else if (res["action"] == "load_track")
					{
						/*
						this.cash = 1000000.00_GBP;
						std::string path = res["path"].asString();
						const char* path_c = path.c_str();

						if (!(createdRideID.IsNull()))
				        {
							auto ride = GetRide(createdRideID);
							//std::cout<<"R1\n";
							createdRideID = RideId::GetNull();

						    // close first...
							auto gameAction1 = RideSetStatusAction(ride->id, RideStatus::closed);
						    //gameAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
						    //});
						    gameAction1.SetFlags(GAME_COMMAND_FLAG_APPLY);

						    GameActions::ExecuteNested(&gameAction1);
							//std::cout<<"R2\n";
						    if (!(ride->lifecycle_flags & RIDE_LIFECYCLE_ON_TRACK))
							{
								ride->lifecycle_flags &= RIDE_LIFECYCLE_ON_TRACK;
							}
						    ride_clear_for_construction(ride);

							auto gameAction2 = RideDemolishAction(ride->id, RIDE_MODIFY_DEMOLISH);
						    gameAction2.SetFlags(GAME_COMMAND_FLAG_APPLY);
						    //gameAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
							//std::cout<<"R3\n";
							//});				
						    GameActions::ExecuteNested(&gameAction2);



						    ClearableItems itemsToClear = 0;
					        itemsToClear |= CLEARABLE_ITEMS::SCENERY_SMALL;
					        itemsToClear |= CLEARABLE_ITEMS::SCENERY_LARGE;
					        itemsToClear |= CLEARABLE_ITEMS::SCENERY_FOOTPATH;

							auto mapSizeMaxXY = GetMapSizeMaxXY();
						    auto range = MapRange(0, 0, mapSizeMaxXY.x, mapSizeMaxXY.y);

						    auto cAction = ClearAction(range, itemsToClear);
							auto res = GameActions::Execute(&cAction);

							//ride_action_modify(&ride, RIDE_MODIFY_DEMOLISH, GAME_COMMAND_FLAG_APPLY);
				        }

					    std::unique_ptr<TrackDesign> _trackDesign = TrackDesignImport(path_c);
						if (_trackDesign != nullptr)
						{
							//_trackDesign->name = "Test";

							RideId _rideIndex{ RideId::GetNull() };

							auto _currentTrackPieceDirection = static_cast<Direction>(0);


							CoordsXYZ trackLoc;
							GameActions::Result res;
							bool found2 = false;
							for (auto &mapCoords : possibleCoords)
							{
							    auto surfaceElement = MapGetSurfaceElementAt(mapCoords);
							    auto mapZ = surfaceElement->GetBaseZ() + TrackDesignGetZPlacement(_trackDesign.get(), GetOrAllocateRide(_rideIndex), { mapCoords, surfaceElement->GetBaseZ() });
								////std::cout<<"mapz:"<<mapZ<<"\n";

							    trackLoc = { mapCoords, mapZ };
								bool found = false;
							    for (int32_t i2 = 0; i2 < 7; i2++, trackLoc.z += 8)
							    {
							        auto tdAction = TrackDesignAction(CoordsXYZD{ trackLoc.x, trackLoc.y, trackLoc.z, _currentTrackPieceDirection }, *_trackDesign);
							        tdAction.SetFlags(0);
							        res = GameActions::Query(&tdAction);

							        // If successful don't keep trying.
							        // If failure due to no money then increasing height only makes problem worse
							        if (res.Error != GameActions::Status::Ok) // || res.Error == GameActions::Status::InsufficientFunds)
							        {
										//std::cout<<"ERR1\n" << res.GetErrorMessage()<<"\n";
							        }
									else
									{
										found = true;
										break;
									}
							    }
								if (found)
								{
									found2 = true;
									break;
								}
							}

							if (!found2)
							{
								//std::cout<<"stopping\n";
								return;
							}
							//std::cout<<"Placing\n";
						    auto tdAction = TrackDesignAction({ trackLoc, _currentTrackPieceDirection }, *_trackDesign);
						    tdAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
						        if (result->Error == GameActions::Status::Ok)
						        {
						            auto rideId = result->GetData<RideId>();
						            auto getRide = get_ride(rideId);
									createdRideID = rideId;
						            if (getRide != nullptr)
						            {
						                //auto intent = Intent(WC_RIDE);
						                //intent.putExtra(INTENT_EXTRA_RIDE_ID, rideId.ToUnderlying());
						                //context_open_intent(&intent);

									    RideSetStatusAction gameAction = RideSetStatusAction(rideId, RideStatus::open);
										gameAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
											//std::cout<<"CALLBACK\n";
											//std::cout<<result->GetErrorMessage()<<"\n";
										});
									    GameActions::ExecuteNested(&gameAction);
						            }
						        }
						        else
						        {
									//std::cout<<"ERR2\n";
								}
						    });
						    res = GameActions::Execute(&tdAction);

						    // send the reply to the client
							////std::cout << "Sending back.\n";
						    //socket.send(zmq::buffer(data), zmq::send_flags::none);
						}
						*/
					}
					else if (res["action"] == "load_park_json")
					{
						std::string path = res["path"].asString();
						//const char* path_c = path.c_str();
				
						OpenRCT2::GetContext()->LoadParkFromFile("/Users/jcampbell/Library/Application Support/OpenRCT2/scenario/My new scenario.park", false, true);
					    OpenRCT2::GetContext()->LoadParkFromFile(path, false, true);
					}
					else if (res["action"] == "close_park")
					{
				        auto parkSetParameterAction = ParkSetParameterAction(ParkParameter::Close);
			            parkSetParameterAction.SetCallback([&](const GameAction* ga, const GameActions::Result* result) {
							socket_send.connect(portAddress2);
							socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
							socket_send.disconnect(portAddress2);
			            });
				        GameActions::Execute(&parkSetParameterAction);
					}
					else if (res["action"] == "open_park")
					{
			            for (auto& rideRef : GetRideManager())
			            {
			                if (rideRef.status != RideStatus::open) // && rideRef.GetClassification() == static_cast<RideClassification>(page))
			                {
			                    auto gameAction = RideSetStatusAction(rideRef.id, RideStatus::open);
					            gameAction.SetCallback([&](const GameAction* ga, const GameActions::Result* result) {
									std::cout<<"done opening ride (open park)\n";
					            });
								
			                    GameActions::Execute(&gameAction);
			                }
			            }
					
				        auto parkSetParameterAction = ParkSetParameterAction(ParkParameter::Open);
			            parkSetParameterAction.SetCallback([&](const GameAction* ga, const GameActions::Result* result) {
							socket_send.connect(portAddress2);
							socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
							socket_send.disconnect(portAddress2);
			            });
				        GameActions::Execute(&parkSetParameterAction);
					}
					else if (res["action"] == "run_sim")
					{
						gGamePaused = false;
						isPaused = false;
					
						int n, m;
						n = gameState.mapSize.x;
						m = gameState.mapSize.y;

						num_ticks = res["num_ticks"].asInt();
						if (num_ticks == -1)
						{
							current_month = GetDate().GetMonthsElapsed();
						}
					
						//std::cout << "size: " << n << " x " << m << "\n";
					
					    visitCounts = new int*[n];
					    for (int i = 0; i < n; ++i) {
					        visitCounts[i] = new int[m];
					    }

					    // Initialize all elements to 0
					    for (int i = 0; i < n; ++i) {
					        for (int j = 0; j < m; ++j) {
					            visitCounts[i][j] = 0;
					        }
					    }
					
						CheatsSet(CheatType::DisableLittering, true);
						CheatsSet(CheatType::BuildInPauseMode, true);
						//ResetAllRideBuildDates();
					}
					else if (res["action"] == "pause")
					{
						gGamePaused = true;
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer("done"), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
						current_month = -1;
						num_ticks = -1;
					}
					else if (res["action"] == "unpause")
					{
						gGamePaused = false;
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer("done"), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "set_speed")
					{
						gGameSpeed = res["speed"].asInt();
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer("set"), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_avg_happiness")
					{
						uint32_t num_guests = 0;
						uint32_t sum_happiness = 0;
						for (auto* peep : EntityList<Guest>())
						{
							num_guests += 1;
							sum_happiness += peep->Happiness;
						}
						float avg_happiness = static_cast<float>(sum_happiness) / static_cast<float>(num_guests);
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(avg_happiness)), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_num_guests")
					{
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(gameState.numGuestsInPark)), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_visit_counts")
					{
						int n, m;
						n = gameState.mapSize.x;
						m = gameState.mapSize.y;
					
					    Json::Value jsonArray(Json::arrayValue);  // Define as an array type

					    // Populate the JSON object with the 2D array data
					    for (int i = 0; i < n; ++i) {
					        Json::Value row(Json::arrayValue);
					        for (int j = 0; j < m; ++j) {
								////std::cout<<"accessing"<<i<<","<<j<<"\n";
								if (visitCounts)
						            row.append(visitCounts[i][j]);
								else
									row.append(0);
					        }
					        jsonArray.append(row);
					    }
					    Json::StreamWriterBuilder writer;
					    std::string jsonString = Json::writeString(writer, jsonArray);
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(jsonString), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);

						if (visitCounts)
						{
						    for (int i = 0; i < n; ++i) {
						        delete[] visitCounts[i];
						    }
						    delete[] visitCounts;
						}
					}
					else if (res["action"] == "get_park_rating")
					{
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(Park::CalculateParkRating())), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_company_value")
					{
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(Park::CalculateCompanyValue())), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_park_value")
					{
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(Park::CalculateParkValue())), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_cash")
					{
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(FinanceGetCurrentCash())), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_loan")
					{
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(gameState.bankLoan)), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_max_loan")
					{
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(gameState.maxBankLoan)), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_weekly_profit")
					{
				        auto currentWeeklyProfit = gameState.weeklyProfitAverageDividend;
				        if (gameState.weeklyProfitAverageDivisor != 0)
				        {
				            currentWeeklyProfit /= gameState.weeklyProfitAverageDivisor;
				        }
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(currentWeeklyProfit)), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_ride_stats")
					{
						int32_t x, y;
						x = res["x"].asInt();//*32;
						y = res["y"].asInt();//*32;
					
						RideId rideIndex = RideId::GetNull();
						bool found = false;
					    TileElementIterator cur_iter;
						cur_iter.x = x;
						cur_iter.y = y;
				        cur_iter.element = MapGetFirstElementAt(TileCoordsXY{ x, y });
						do {
							TileElement* cur_element = cur_iter.element;
							if (cur_element->GetType() == TileElementType::Track)
							{
								auto trackEl = cur_element->AsTrack();
								rideIndex = trackEl->GetRideIndex();
								found = true;
								break;
							}
							else if (cur_element->GetType() == TileElementType::Entrance)
							{
								auto entranceEl = cur_element->AsEntrance();
								rideIndex = entranceEl->GetRideIndex();
								found = true;
								break;
							}
						} while(!(cur_iter.element++)->IsLastForTile());
					
						if (!found)
						{
							socket_send.connect(portAddress2);
							socket_send.send(zmq::buffer("can't find ride"), zmq::send_flags::none);
							socket_send.disconnect(portAddress2);
						}
						else
						{
							auto ride = GetRide(rideIndex);
					
						    Json::Value event;  // Define as an array type
					
							event["popularity"] = ride->popularity;
							event["excitement"] = ride->ratings.excitement;
							event["intensity"] = ride->ratings.intensity;
							event["nausea"] = ride->ratings.nausea;
							event["profit"] = ride->profit;
					
						    Json::StyledWriter styledWriter;
							socket_send.connect(portAddress2);
							socket_send.send(zmq::buffer(styledWriter.write(event)), zmq::send_flags::none);
							socket_send.disconnect(portAddress2);
						}
					}
					else if (res["action"] == "get_guest_thoughts")
					{
						int hungry, thirsty, toilet, cantfind, notpaying;
						hungry = thirsty = toilet = cantfind = notpaying = 0;
						for (auto* peep : EntityList<Guest>())
						{
				            for (int32_t i = 0; i < kPeepMaxThoughts; ++i)
				            {
			                    const auto& thought = peep->Thoughts[i];
								if (thought.type != PeepThoughtType::None && thought.freshness <= 5)
								{
									if (thought.type == PeepThoughtType::Hungry)
										hungry += 1;
									else if (thought.type == PeepThoughtType::Thirsty)
										thirsty += 1;
									else if (thought.type == PeepThoughtType::Toilet)
										toilet += 1;
									else if (thought.type == PeepThoughtType::CantFind)
										cantfind += 1;
									else if (thought.type == PeepThoughtType::NotPaying)
										notpaying += 1;
								}
							}
						}
						
					    Json::Value event;
						event["hungry"] = hungry;
						event["thirsty"] = thirsty;
						event["toilet"] = toilet;
						event["cantfind"] = cantfind;
						event["notpaying"] = notpaying;
					
					    Json::StyledWriter styledWriter;
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(styledWriter.write(event)), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_awards")
					{
						Json::Value event;
					    auto& currentAwards = gameState.currentAwards;
					    for (auto& award : currentAwards)
						{
							Json::Value base_field;
							base_field["type"] = std::to_string(static_cast<uint16_t>(award.Type));
							base_field["time"] = std::to_string(award.Time);
							event.append(base_field);
						}
					    Json::StreamWriterBuilder writer;
					    std::string jsonString = Json::writeString(writer, event);
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(jsonString), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_num_months")
					{
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(std::to_string(GetDate().GetMonthsElapsed())), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "save_park")
					{
						std::string path = res["fname"].asString();
						SaveGameWithName(path);
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer("set"), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "load_objects")
					{
	                    /*const auto* rideEntry = GetRideEntryByIndex(entryIndex);
	                    auto rideType = rideEntry->GetFirstNonNullRideType();
	                    ResearchCategory category = static_cast<ResearchCategory>(getRideTypeDescriptor(rideType).Category);
	                    ResearchInsertRideEntry(rideType, entryIndex, category, true);*/
					
					    /*for (ObjectEntryIndex i = 0; i < MAX_RIDE_OBJECTS; i++)
					    {
					        //const auto* rideEntry = GetRideEntryByIndex(i);
		                    RideEntrySetInvented(i);
		                    ResearchInsertRideEntry(i, true);
					    }*/
						
				        auto& objManager = GetContext()->GetObjectManager();
				        int32_t numItems = static_cast<int32_t>(ObjectRepositoryGetItemsCount());
				        const ObjectRepositoryItem* items = ObjectRepositoryGetItems();
				        for (int32_t i = 0; i < numItems; i++)
				        {
			                const auto* item = &items[i];
							if (item->Type == ObjectType::ride)
							{
								bool matchedSource = false;
					            for (auto source : item->Sources)
					            {
					                if (source == ObjectSourceGame::RCT1 || source == ObjectSourceGame::AddedAttractions || source == ObjectSourceGame::LoopyLandscapes || source == ObjectSourceGame::RCT2)
									{
										matchedSource = true;
										break;
									}
								}
								if (!matchedSource)
									continue;
								
				                auto descriptor = ObjectEntryDescriptor(*item);
				                const auto* loadedObject = objManager.GetLoadedObject(descriptor);
				                if (loadedObject == nullptr)
				                {
				                    loadedObject = objManager.LoadObject(descriptor);
				                    if (loadedObject != nullptr)
									{
				                        // Defaults selected items to researched (if in-game)
				                        auto objectType = loadedObject->GetObjectType();
				                        auto entryIndex = ObjectManagerGetLoadedObjectEntryIndex(loadedObject);
				                        if (objectType == ObjectType::ride)
				                        {
				                            const auto* rideEntry = GetRideEntryByIndex(entryIndex);
				                            auto rideType = rideEntry->GetFirstNonNullRideType();
				                            ResearchCategory category = static_cast<ResearchCategory>(GetRideTypeDescriptor(rideType).Category);
				                            ResearchInsertRideEntry(rideType, entryIndex, category, true);
				                        }
				                    }
				                }
							}
				        }
					
						/*
					    for (int32_t i = 0; i < MAX_RIDE_OBJECTS; i++)
					    {
					        const auto* rideEntry = GetRideEntryByIndex(i);
					        if (rideEntry == nullptr)
					        {
					            continue;
					        }

					        for (auto rideType : rideEntry->ride_type)
					        {
					            if (rideType != RIDE_TYPE_NULL)
					            {
					                ResearchCategory category = getRideTypeDescriptor(rideType).GetResearchCategory();
					                ResearchInsertRideEntry(rideType, i, category, true);
					            }
					        }
					    }*/
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer("set"), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "get_available_rides")
					{
					    Json::Value event;
					
			            bool buttonForRideTypeCreated = false;
			            bool allowDrawingOverLastButton = false;

			            //uint8_t highestVehiclePriority = 0;
					
			            // For each ride type in the view order list
			            for (int32_t i = 0; i < static_cast<int32_t>(std::size(RideTypeViewOrder2)); i++)
			            {
			                auto rideType = RideTypeViewOrder2[i];
			                if (rideType == kRideTypeNull)
			                    continue;
					
				            auto& objManager = OpenRCT2::GetContext()->GetObjectManager();
				            auto& rideEntries = objManager.GetAllRideEntries(rideType);
				            for (auto rideEntryIndex : rideEntries)
				            {
				                // Skip if vehicle type is not invented yet
				                if (!RideEntryIsInvented(rideEntryIndex) && !getGameState().cheats.ignoreResearchStatus)
				                    continue;

				                // Ride entries
				                const auto* rideEntry = GetRideEntryByIndex(rideEntryIndex);

				                // Skip if the vehicle isn't the preferred vehicle for this generic track type
			                
								/*if (!Config::Get().interface.ListRideVehiclesSeparately
				                    && !getRideTypeDescriptor(rideType).HasFlag(RIDE_TYPE_FLAG_LIST_VEHICLES_SEPARATELY)
				                    && highestVehiclePriority > rideEntry->BuildMenuPriority)
				                {
				                    continue;
				                }*/
								void* x{};
							    std::string s = FormatStringIDLegacy(rideEntry->naming.Name, x);

				                //highestVehiclePriority = rideEntry->BuildMenuPriority;

				                // Determines how and where to draw a button for this ride type/vehicle.
				                if (true) //Config::Get().interface.ListRideVehiclesSeparately
				                //    || getRideTypeDescriptor(rideType).HasFlag(RIDE_TYPE_FLAG_LIST_VEHICLES_SEPARATELY))
				                {
				                    // Separate, draw apart
				                    allowDrawingOverLastButton = false;

				                    //if (nextListItem >= listEnd)
				                    //    continue;

									Json::Value base_field;
									base_field["type"] = std::to_string(rideType);
									base_field["entry_index"] = std::to_string(rideEntryIndex);
									base_field["name"] = s;
									event.append(base_field);

				                }
				                else if (!buttonForRideTypeCreated)
				                {
				                    // Non-separate, draw-apart
				                    buttonForRideTypeCreated = true;
				                    allowDrawingOverLastButton = true;

				                    //if (nextListItem >= listEnd)
				                    //    continue;

									Json::Value base_field;
									base_field["type"] = std::to_string(rideType);
									base_field["entry_index"] = std::to_string(rideEntryIndex);
									base_field["name"] = s;
									event.append(base_field);
				                }
				                else if (allowDrawingOverLastButton)
				                {
				                    // Non-separate, draw over previous
				                    if (rideType == rideEntry->ride_type[0])
				                    {
										Json::Value base_field;
										base_field["type"] = std::to_string(rideType);
										base_field["entry_index"] = std::to_string(rideEntryIndex);
										base_field["name"] = s;
										event.append(base_field);
				                    }
				                }
				            }
						}
					
						/*
					    Json::StyledWriter styledWriter;
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(styledWriter.write(event)), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
						*/
					
					    Json::StreamWriterBuilder writer;
					    std::string jsonString = Json::writeString(writer, event);
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(jsonString), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else if (res["action"] == "place_ride")
					{
						int32_t type = res["ride_type"].asInt();
						//int32_t subtype = res["ride_subtype"].asInt();
					
						//auto subtype_str = res["ride_subtype"].asString();
					    //auto& objectMgr = OpenRCT2::GetContext()->GetObjectManager();
			            //auto entryIndex = objectMgr.GetLoadedObjectEntryIndex(identifier); //subtype;
										
				        //int32_t rideEntryIndex = RideGetEntryIndex(type, subtype);
					
						int32_t x, y, z, entrance_x, entrance_y, exit_x, exit_y, entrance_dir, exit_dir, entrance_z, exit_z, track_dir;
						x = res["x"].asInt()*32;
						y = res["y"].asInt()*32;
						z = res["z"].asInt();
						entrance_x = res["entrance_x"].asInt()*32;
						entrance_y = res["entrance_y"].asInt()*32;
						entrance_z = res["entrance_z"].asInt();
						exit_x = res["exit_x"].asInt()*32;
						exit_y = res["exit_y"].asInt()*32;
						exit_z = res["exit_z"].asInt();
						entrance_dir = res["entrance_dir"].asInt();
						exit_dir = res["exit_dir"].asInt();
						track_dir = res["track_dir"].asInt();
						int64_t price = res["price"].asInt();
						
						std::string entry_name = res["ride_entry_name"].asString();
						int32_t subtype = kObjectEntryIndexNull;
						
				        int32_t colour1 = RideGetRandomColourPresetIndex(type);
				        int32_t colour2 = RideGetUnusedPresetVehicleColour(subtype);
						
						if (entry_name != "default")
						{
						    for (int32_t i = 0; i < kMaxRideObjects; i++)
						    {
						        const auto* rideEntry = GetRideEntryByIndex(i);
						        if (rideEntry == nullptr)
						        {
						            continue;
						        }
								void* sp{};
							    std::string s = FormatStringIDLegacy(rideEntry->naming.Name, sp);
								
								if (s == entry_name)
								{
									subtype = i;
									break;
								}
							}
						}
					    
						
						//if (price == -1) std::cout <<"default\n";

				        auto gameAction = RideCreateAction(type, subtype, colour1, colour2, OpenRCT2::getGameState().lastEntranceStyle);
						////std::cout<<"A\n";
				        gameAction.SetCallback([&x, &y, &z, &entrance_x, &entrance_y, &exit_x, &exit_y, &price, &entrance_dir, &exit_dir, &entrance_z, &exit_z, &track_dir](const GameAction* ga, const GameActions::Result* result) {
				            if (result->Error != GameActions::Status::Ok)
							{
								//std::cout<<result->GetErrorMessage()<<"\n";
								socket_send.connect(portAddress2);
								socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
								socket_send.disconnect(portAddress2);
							}
							////std::cout<<"B\n";
						
				            const auto rideIndex = result->GetData<RideId>();
				            auto ride = GetRide(rideIndex);
				           	//RideConstructionStart(*ride);
						
							if (ride == nullptr)
							{
								socket_send.connect(portAddress2);
								socket_send.send(zmq::buffer("ride is null"), zmq::send_flags::none);
								socket_send.disconnect(portAddress2);
							}
							else
							{
					            RideId rideIndex2;
								//TrackElemType trackType = OpenRCT2::TrackElemType::None;
					            int32_t properties;
								uint8_t trackDirection;
					            CoordsXYZ trackPos {};
								SelectedLiftAndInverted liftHillAndInvertedState{};
								
						        //trackType = 0; // return std::make_tuple(false, 0);
								trackDirection = 0;
								properties = 4 << 12; //0;
								rideIndex2 = rideIndex;								
								
								TrackElemType trackType = ride->getRideTypeDescriptor().StartTrackPiece; //GetTrackTypeFromCurve(ride->getRideTypeDescriptor().StartTrackPiece.curve, false, TrackPitch::None, TrackPitch::None, TrackRoll::None, TrackRoll::None);
								/*const uint16_t curve = static_cast<uint16_t>(ride->getRideTypeDescriptor().StartTrackPiece); // | RideConstructionSpecialPieceSelected;
							    if (curve <= 8)
							    {
									bool startsDiagonal = false;
									
							        for (uint32_t i = 0; i < std::size(TrackMetaData::gTrackDescriptors); i++)
							        {
							            const TrackMetaData::TrackDescriptor* trackDescriptor = &TrackMetaData::gTrackDescriptors[i];

							            if (EnumValue(trackDescriptor->trackCurve) != curve)
							                continue;
							            if (trackDescriptor->startsDiagonally != startsDiagonal)
							                continue;
							            if (trackDescriptor->slopeStart != TrackPitch::None)
							                continue;
							            if (trackDescriptor->slopeEnd != TrackPitch::None)
							                continue;
							            if (trackDescriptor->rollStart != TrackRoll::None)
							                continue;
							            if (trackDescriptor->rollEnd != TrackRoll::None)
							                continue;
										
										trackType = trackDescriptor->trackElement;
										break;
							            //return std::make_tuple(true, trackDescriptor->trackElement);
							        }
							    }
								else
								{
									trackType = curve & 0xFFFF;
								}
								*/
								//std::cout<< "curve: " << curve <<"\n";
								//std::cout << "A " << trackType << " " << trackDirection << " " << liftHillAndAlternativeState << " " << properties << "\n";
				            
					            /*if (WindowRideConstructionUpdateState(
					                    &trackType, &trackDirection, &rideIndex2, &liftHillAndAlternativeState, &trackPos, &properties))
								{
									socket_send.connect(portAddress2);
									socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
									socket_send.disconnect(portAddress2);
								}
								std::cout << "B " << trackType << " " << trackDirection << " " << liftHillAndAlternativeState << " " << properties << "\n";*/

							
								if (z == 0)
								{
							    	auto surfaceElement = MapGetSurfaceElementAt(CoordsXY{ x, y });
									z = surfaceElement->GetBaseZ();
								}
							
								trackPos.x = x;
								trackPos.y = y;
								trackPos.z = z; //mapZ; //112;
								if (track_dir > -1)
								{
									trackDirection = track_dir;
								}
				            
								auto trackPlaceAction = TrackPlaceAction(rideIndex2, trackType, ride->type, { trackPos, trackDirection }, properties & 0xFF, (properties >> 8) & 0x0F, (properties >> 12) & 0x0F, liftHillAndInvertedState, false);
								trackPlaceAction.SetCallback([&entrance_x, &entrance_y, &exit_x, &exit_y, &ride, &rideIndex2, &price, &entrance_dir, &exit_dir, &entrance_z, &exit_z](const GameAction*, const GameActions::Result* result) {
									//std::cout<<"D\n";
								
						            if (result->Error != GameActions::Status::Ok)
									{
										//std::cout<<result->GetErrorMessage()<<"\n";
										socket_send.connect(portAddress2);
										socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
										socket_send.disconnect(portAddress2);
									}
									else
									{
									    //RideSetStatusAction closeGameAction = RideSetStatusAction(rideIndex2, RideStatus::closed);
										/*closeGameAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
											//std::cout<<"E\n";
									
											socket_send.connect(portAddress2);
											socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
											socket_send.disconnect(portAddress2);
											//std::cout<<result->GetErrorMessage()<<"\n";
										});*/
									    //GameActions::Execute(&closeGameAction);
										
										
										if (price > -1)
										{
								            auto rideSetPriceAction = RideSetPriceAction(rideIndex2, price, true);
								            GameActions::Execute(&rideSetPriceAction);
								            //auto rideSetPriceAction2 = RideSetPriceAction(rideIndex, price, false);
								            //GameActions::Execute(&rideSetPriceAction2);
											//std::cout<<"setting price to"<<price<<"\n";
										}
										else
										{
											//std::cout<<"not setting price:"<<price<<"\n";
										}
									
									    const auto& rtd = ride->getRideTypeDescriptor();
										if (rtd.HasFlag(RtdFlag::isShopOrFacility))
										{
											auto openGameAction = RideSetStatusAction(rideIndex2, RideStatus::open);
											openGameAction.SetCallback([&](const GameAction* ga, const GameActions::Result* result) {
												socket_send.connect(portAddress2);
												socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
												socket_send.disconnect(portAddress2);
											});
											auto res5 = GameActions::Execute(&openGameAction);
										}
										else
										{ // place entrance
										
											if (entrance_z == 0)
											{
										    	auto surfaceElement = MapGetSurfaceElementAt(CoordsXY{ entrance_x, entrance_y });
												entrance_z = surfaceElement->GetBaseZ();
											}
										
											if (entrance_dir == -1)
											{
												bool found = false;
										        for (uint8_t directionIncrement = 0; directionIncrement < 4; directionIncrement++)
										        {
										            entrance_dir = (0 + directionIncrement) & 3;
										            // search for TrackElement one tile over, shifted in the search direction
													CoordsXY nextLocation = {entrance_x, entrance_y};
										            nextLocation += CoordsDirectionDelta[entrance_dir];
											
									                auto* tileElement = MapGetFirstElementAt(nextLocation);
									                if (tileElement == nullptr)
									                    continue;
									                do
									                {
									                    if (tileElement->GetType() != TileElementType::Track)
															continue;
														auto trackEl = tileElement->AsTrack();
														if (trackEl->GetRideIndex() == rideIndex2) //if (nextLocation.x == x and nextLocation.y == y)
														{
															found = true;
															break;
														}
									                } while (!(tileElement++)->IsLastForTile());

								                    if (found) break;
												}
												if (!found)
												{
													/*socket_send.connect(portAddress2);
													socket_send.send(zmq::buffer("ride not found near entrance?"), zmq::send_flags::none);
													socket_send.disconnect(portAddress2);*/
													entrance_dir = 0;
												}
											}
										
								            CoordsXYZD entranceCoords = {entrance_x, entrance_y, entrance_z, static_cast<Direction>(entrance_dir)};
										
								            auto rideEntranceExitPlaceAction = RideEntranceExitPlaceAction(entranceCoords, entranceCoords.direction, rideIndex2, StationIndex::FromUnderlying(0), false);
											//std::cout<<"E3\n";
								            rideEntranceExitPlaceAction.SetCallback([&exit_z, &exit_x, &exit_y, &rideIndex2, &ride, &exit_dir](const GameAction* ga, const GameActions::Result* result)
											{ 
												//std::cout<<"F\n";
											
												//std::cout<<result->GetErrorMessage()<<"\n";
											
												if (result->Error == GameActions::Status::Ok)
												{ // place exit
													//std::cout<<"G\n";
												
												    //auto surfaceExitElement = MapGetSurfaceElementAt(CoordsXY{ exit_x, exit_y });
												    //auto exitZ = surfaceExitElement->GetBaseZ();
												
													if (exit_z == 0)
													{
												    	auto surfaceElement = MapGetSurfaceElementAt(CoordsXY{ exit_x, exit_y });
														exit_z = surfaceElement->GetBaseZ();
													}
													if (exit_dir == -1)
													{
														bool found = false;
												        for (uint8_t directionIncrement = 0; directionIncrement < 4; directionIncrement++)
												        {
												            exit_dir = (0 + directionIncrement) & 3;
												            // search for TrackElement one tile over, shifted in the search direction
															CoordsXY nextLocation = {exit_x, exit_y};
												            nextLocation += CoordsDirectionDelta[exit_dir];
											
											                auto* tileElement = MapGetFirstElementAt(nextLocation);
											                if (tileElement == nullptr)
											                    continue;
											                do
											                {
											                    if (tileElement->GetType() != TileElementType::Track)
																	continue;
											
																auto trackEl = tileElement->AsTrack();
																if (trackEl->GetRideIndex() == rideIndex2) //if (nextLocation.x == x and nextLocation.y == y)
																{
																	found = true;
																	break;
																}
											                } while (!(tileElement++)->IsLastForTile());

										                    if (found) break;
														}
														if (!found)
														{
															socket_send.connect(portAddress2);
															socket_send.send(zmq::buffer("ride not found near entrance?"), zmq::send_flags::none);
															socket_send.disconnect(portAddress2);
														}
														//exit_dir = DirectionReverse(exit_dir);
													}
												
										            CoordsXYZD exitCoords = {exit_x, exit_y, exit_z, static_cast<Direction>(exit_dir)};
													//std::cout<<"entrance z: " << entrance_z << "; exit z: " << exit_z << "\n";
										            auto rideEntranceExitPlaceAction = RideEntranceExitPlaceAction(exitCoords, exitCoords.direction, rideIndex2, StationIndex::FromUnderlying(0), true);
										            rideEntranceExitPlaceAction.SetCallback([&rideIndex2, &ride](const GameAction* ga, const GameActions::Result* result) {
													
													    auto rideSetSettingAction = RideSetSettingAction(rideIndex2, RideSetSetting::Departure, ride->departFlags ^ RIDE_DEPART_WAIT_FOR_LOAD);
														rideSetSettingAction.SetCallback([&](const GameAction* ga, const GameActions::Result* result) {
															auto openGameAction = RideSetStatusAction(rideIndex2, RideStatus::open);
															openGameAction.SetCallback([&](const GameAction* ga, const GameActions::Result* result) {
																socket_send.connect(portAddress2);
																socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
																socket_send.disconnect(portAddress2);
															});
															auto res5 = GameActions::Execute(&openGameAction);
														});
													    auto res4 = GameActions::Execute(&rideSetSettingAction);
													
														//std::cout<<"H\n";
														//std::cout<<result->GetErrorMessage()<<"\n";
										            });
										            auto res2 = GameActions::Execute(&rideEntranceExitPlaceAction);
												
												}
												else
												{
													socket_send.connect(portAddress2);
													socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
													socket_send.disconnect(portAddress2);
												}
											
											
								            });
								            auto res3 = GameActions::Execute(&rideEntranceExitPlaceAction);
										
										}
									
									}
									////std::cout<<"D\n";
									/*
								    RideSetStatusAction gameAction = RideSetStatusAction(rideIndex, RideStatus::open);
									gameAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
										//std::cout<<"E\n";
									
										socket_send.connect(portAddress2);
										socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
										socket_send.disconnect(portAddress2);
										//std::cout<<result->GetErrorMessage()<<"\n";
									});
								    GameActions::ExecuteNested(&gameAction);*/
								});
					            GameActions::Execute(&trackPlaceAction);
				            }
				        });

				        GameActions::Execute(&gameAction);
					}
					else if (res["action"] == "place_path")
					{
						int32_t x, y, z;
						x = res["x"].asInt()*32;
						y = res["y"].asInt()*32;
						z = res["z"].asInt();
					
				        //for (const auto& parkEntrance : gameState.park.Entrances)
						//	//std::cout<<"entrance"<<parkEntrance.x<<","<<parkEntrance.y<<","<<parkEntrance.z<<"\n";
						//CoordsXY iter = {res["x"].asInt(), res["y"].asInt()};
						bool isQueue = res["queue"].asInt() == 1;
						/*TileElementIterator cur_iter; // int32_t x, y
						cur_iter.x = iter.x;
						cur_iter.y = iter.y;
					
						cur_iter.element = MapGetFirstElementAt(TileCoordsXY{ iter.x, iter.y });
						do {
							TileElement* cur_element = cur_iter.element;
							if (cur_element->GetType() == TileElementType::Surface)
							{
								auto surfaceEl = cur_element->AsSurface();
								//if ((surfaceEl->GetOwnership() & OWNERSHIP_OWNED))
								//	owned = true;
								break;
							}
						} while(!(cur_iter.element++)->IsLastForTile());
						*/
						/*uint8_t DefaultPathSlope[] = {
						    0,
						    SLOPE_IS_IRREGULAR_FLAG,
						    SLOPE_IS_IRREGULAR_FLAG,
						    FOOTPATH_PROPERTIES_FLAG_IS_SLOPED | 2,
						    SLOPE_IS_IRREGULAR_FLAG,
						    SLOPE_IS_IRREGULAR_FLAG,
						    FOOTPATH_PROPERTIES_FLAG_IS_SLOPED | 3,
						    RAISE_FOOTPATH_FLAG,
						    SLOPE_IS_IRREGULAR_FLAG,
						    FOOTPATH_PROPERTIES_FLAG_IS_SLOPED | 1,
						    SLOPE_IS_IRREGULAR_FLAG,
						    RAISE_FOOTPATH_FLAG,
						    FOOTPATH_PROPERTIES_FLAG_IS_SLOPED | 0,
						    RAISE_FOOTPATH_FLAG,
						    RAISE_FOOTPATH_FLAG,
						    SLOPE_IS_IRREGULAR_FLAG,
						};*/
					
						if (z == 0)
						{
					    	auto surfaceElement = MapGetSurfaceElementAt(CoordsXY{ x, y });
							z = surfaceElement->GetBaseZ();
						}
						//std::cout<<"z: " << z << "\n";
						/*
						// get default z
						TileElementIterator cur_iter; // int32_t x, y
						cur_iter.x = gameState.park.Entrances[0].x;
						cur_iter.y = gameState.park.Entrances[0].y;
					
						cur_iter.element = MapGetFirstElementAt(TileCoordsXY{ iter.x, iter.y });
						do {
							TileElement* cur_element = cur_iter.element;
							if (cur_element->GetType() == TileElementType::Entrance)
							{
								break;
							}
						} while(!(cur_iter.element++)->IsLastForTile());
					
			            auto z = cur_iter.element->GetBaseZ();
						*/
					
			            auto slope = 0; // DefaultPathSlope[cur_iter.element->AsSurface()->GetSlope() & kTileSlopeRaisedCornersMask];
						FootpathSelectDefault();
			            auto selectedType = FootpathGetDefaultSurface(isQueue); // FootpathSelection.NormalSurface; //gFootpathSelection.GetSelectedSurface();
			            PathConstructFlags constructFlags = 0; // FootpathCreateConstructFlags(type);
						if (isQueue)
						{
							constructFlags |= PathConstructFlag::IsQueue;
						}
						//std::cout<<"x"<<iter.x*32<<",y"<<iter.y*32<<",z"<<z<<"\n";

						for (uint8_t _direction = 0; _direction < 4; _direction++)
						{
				            auto zLow = z;
				            auto zHigh = z + kPathClearance;
				            WallRemoveIntersectingWalls(
				                { {x, y}, zLow, zHigh + ((slope & kTileSlopeRaisedCornersMask) ? 16 : 0) }, DirectionReverse(_direction));
				            WallRemoveIntersectingWalls(
				                { x - CoordsDirectionDelta[_direction].x, y - CoordsDirectionDelta[_direction].y, zLow, zHigh },
				                _direction);
						}


			            auto footpathPlaceAction = FootpathPlaceAction(
			                { x, y, z }, slope, selectedType, gFootpathSelection.Railings, kInvalidDirection, constructFlags);
			            footpathPlaceAction.SetCallback([&](const GameAction* ga, const GameActions::Result* result) {
							socket_send.connect(portAddress2);
							socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
							socket_send.disconnect(portAddress2);
			            });
			            GameActions::Execute(&footpathPlaceAction);
					}
					else if (res["action"] == "remove_ride")
					{
						int32_t x, y, z;
						x = res["x"].asInt();//*32;
						y = res["y"].asInt();//*32;
						z = res["z"].asInt();
					
						RideId rideIndex = RideId::GetNull();
						if (z == 0)
						{
							bool found = false;
						    TileElementIterator cur_iter;
							cur_iter.x = x;
							cur_iter.y = y;
					        cur_iter.element = MapGetFirstElementAt(TileCoordsXY{ x, y });
							do {
								TileElement* cur_element = cur_iter.element;
								if (cur_element->GetType() == TileElementType::Track)
								{
									auto trackEl = cur_element->AsTrack();
									rideIndex = trackEl->GetRideIndex();
									found = true;
									break;
								}
								else if (cur_element->GetType() == TileElementType::Entrance)
								{
									auto entranceEl = cur_element->AsEntrance();
									rideIndex = entranceEl->GetRideIndex();
									found = true;
									break;
								}
							} while(!(cur_iter.element++)->IsLastForTile());
						
							if (!found)
							{
								socket_send.connect(portAddress2);
								socket_send.send(zmq::buffer("can't find ride"), zmq::send_flags::none);
								socket_send.disconnect(portAddress2);
							}
						}
						else
						{
							auto trackEl = MapGetTrackElementAt(CoordsXYZ {x*32, y*32, z});
							if (trackEl != nullptr)
							{
								rideIndex = trackEl->GetRideIndex();
							}
							else
							{
								auto entranceEl = MapGetRideEntranceElementAt(CoordsXYZ{x*32, y*32, z}, false);
								if (entranceEl != nullptr)
								{
									rideIndex = entranceEl->GetRideIndex();
								}
								else
								{
									socket_send.connect(portAddress2);
									socket_send.send(zmq::buffer("can't find ride"), zmq::send_flags::none);
									socket_send.disconnect(portAddress2);
								}
							}
						}
						assert(rideIndex != RideId::GetNull());
				
					    auto closeAction = RideSetStatusAction(rideIndex, RideStatus::closed);
						closeAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
							if (result->Error == GameActions::Status::Ok)
							{
								auto gameAction = RideDemolishAction(rideIndex, RideModifyType::demolish);
					            gameAction.SetCallback([&](const GameAction* ga, const GameActions::Result* result) {
									socket_send.connect(portAddress2);
									socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
									socket_send.disconnect(portAddress2);
					            });
						        GameActions::Execute(&gameAction);
							}
							else
							{
								socket_send.connect(portAddress2);
								socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
								socket_send.disconnect(portAddress2);
							}
						});
					    GameActions::Execute(&closeAction);
					}
					else if (res["action"] == "modify_ride_price")
					{
						int32_t x, y, z;
						x = res["x"].asInt();//*32;
						y = res["y"].asInt();//*32;
						z = res["z"].asInt();
						int64_t price = res["price"].asInt();
					
						RideId rideIndex = RideId::GetNull();
						if (z == 0)
						{
							bool found = false;
						    TileElementIterator cur_iter;
							cur_iter.x = x;
							cur_iter.y = y;
					        cur_iter.element = MapGetFirstElementAt(TileCoordsXY{ x, y });
							do {
								TileElement* cur_element = cur_iter.element;
								if (cur_element->GetType() == TileElementType::Track)
								{
									auto trackEl = cur_element->AsTrack();
									rideIndex = trackEl->GetRideIndex();
									found = true;
									break;
								}
								else if (cur_element->GetType() == TileElementType::Entrance)
								{
									auto entranceEl = cur_element->AsEntrance();
									rideIndex = entranceEl->GetRideIndex();
									found = true;
									break;
								}
							} while(!(cur_iter.element++)->IsLastForTile());
						
							if (!found)
							{
								socket_send.connect(portAddress2);
								socket_send.send(zmq::buffer("can't find ride"), zmq::send_flags::none);
								socket_send.disconnect(portAddress2);
							}
						}
						else
						{
							auto trackEl = MapGetTrackElementAt(CoordsXYZ {x*32, y*32, z});
							if (trackEl != nullptr)
							{
								rideIndex = trackEl->GetRideIndex();
							}
							else
							{
								auto entranceEl = MapGetRideEntranceElementAt(CoordsXYZ{x*32, y*32, z}, false);
								if (entranceEl != nullptr)
								{
									rideIndex = entranceEl->GetRideIndex();
								}
								else
								{
									socket_send.connect(portAddress2);
									socket_send.send(zmq::buffer("can't find ride"), zmq::send_flags::none);
									socket_send.disconnect(portAddress2);
								}
							}
						}
					
						if (rideIndex == RideId::GetNull()) {
							socket_send.connect(portAddress2);
							socket_send.send(zmq::buffer("err"), zmq::send_flags::none);
							socket_send.disconnect(portAddress2);
						}
						else {
				            auto rideSetPriceAction = RideSetPriceAction(rideIndex, price, true);
							rideSetPriceAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
								socket_send.connect(portAddress2);
								socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
								socket_send.disconnect(portAddress2);
							});
				            GameActions::Execute(&rideSetPriceAction);
						}
					}
					else if (res["action"] == "set_park_entry_fee")
					{
						int64_t price = res["price"].asInt();
	                    auto gameAction = ParkSetEntranceFeeAction(price);
						gameAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
							socket_send.connect(portAddress2);
							socket_send.send(zmq::buffer(std::to_string(static_cast<uint16_t>(result->Error))), zmq::send_flags::none);
							socket_send.disconnect(portAddress2);
						});
	                    GameActions::Execute(&gameAction);
					}
					else if (res["action"] == "get_paths")
					{
					    Json::Value event;
					
						for (const auto& parkEntrance : gameState.park.Entrances)
						{
							Json::Value cur_field;
							cur_field["x"] = parkEntrance.x;
							cur_field["y"] = parkEntrance.y;
							cur_field["z"] = parkEntrance.z;
							event["park_entrances"].append(cur_field);
						}
					
					    TileElementIterator iter;
					    TileElementIteratorBegin(&iter);
					    do
					    {
							/*if (!MapIsLocationOwnedOrHasRights(CoordsXY{ iter.x * 32, iter.y * 32 }))
							{
								continue;
							}*/
						
							// check if surface is owned or not.
							bool owned = false;
						    TileElementIterator cur_iter;
							cur_iter.x = iter.x;
							cur_iter.y = iter.y;
					        cur_iter.element = MapGetFirstElementAt(TileCoordsXY{ iter.x, iter.y });
							do {
								TileElement* cur_element = cur_iter.element;
								if (cur_element->GetType() == TileElementType::Surface)
								{
									auto surfaceEl = cur_element->AsSurface();
									//if ((surfaceEl->GetOwnership() & OWNERSHIP_OWNED)) // || (surfaceEl->GetOwnership() & OWNERSHIP_CONSTRUCTION_RIGHTS_OWNED))
									if ((surfaceEl->GetOwnership() & OWNERSHIP_OWNED) || (surfaceEl->GetOwnership() & OWNERSHIP_CONSTRUCTION_RIGHTS_OWNED))
									{
										owned = true;
									}
									break;
								}
							} while(!(cur_iter.element++)->IsLastForTile());
					
							if (cur_iter.x == iter.x and cur_iter.y == iter.y and !owned)
							{
								continue;
							}
						
							auto surface = MapGetSurfaceElementAt(TileCoordsXY{ iter.x, iter.y });
						
							Json::Value base_field;
							base_field["x"] = std::to_string(iter.x);
							base_field["y"] = std::to_string(iter.y);
							base_field["z"] = static_cast<int32_t>(surface->GetBaseZ());
					
					
							TileElement* element = iter.element;
						
							if (element->GetType() == TileElementType::Path)
							{
								auto pathEl = iter.element->AsPath();
							
								Json::Value cur_field;
								cur_field["x"] = std::to_string(iter.x);
								cur_field["y"] = std::to_string(iter.y);
								cur_field["z"] = static_cast<int32_t>(iter.element->GetBaseZ());
								cur_field["queue"] = pathEl->IsQueue(); // bool
								cur_field["is_sloped"] = pathEl->IsSloped();
								base_field["z"] = cur_field["z"];
								event["paths"].append(cur_field);
							}
							else if (element->GetType() == TileElementType::Entrance)
							{
								auto entranceEl = iter.element->AsEntrance();
								if (entranceEl->GetEntranceType() == ENTRANCE_TYPE_RIDE_ENTRANCE || entranceEl->GetEntranceType() == ENTRANCE_TYPE_RIDE_EXIT)
								{
									auto rideIndex = entranceEl->GetRideIndex();
									Ride* ride = GetRide(rideIndex);
									if (ride != nullptr)
									{
										Json::Value cur_field;
										cur_field["x"] = std::to_string(iter.x);
										cur_field["y"] = std::to_string(iter.y);
										cur_field["z"] = static_cast<int32_t>(iter.element->GetBaseZ());
										cur_field["ride_type"] = ride->type;
										cur_field["price"] = ride->price[0];
										cur_field["ride_index"] = static_cast<uint16_t>(rideIndex.ToUnderlying());
										cur_field["direction"] = entranceEl->GetDirection();
										if (entranceEl->GetEntranceType() == ENTRANCE_TYPE_RIDE_ENTRANCE)
											cur_field["entrance_type"] = "entrance";
										else
											cur_field["entrance_type"] = "exit";
										event["ride_entrances"].append(cur_field);
									}
								}
							}
							else if (element->GetType() == TileElementType::Track)
							{
								auto trackEl = iter.element->AsTrack();
								auto rideIndex = trackEl->GetRideIndex();
								Ride* ride = GetRide(rideIndex);
							    const auto& rtd = ride->getRideTypeDescriptor();
								Json::Value cur_field;
								cur_field["x"] = std::to_string(iter.x);
								cur_field["y"] = std::to_string(iter.y);
								cur_field["z"] = static_cast<int32_t>(iter.element->GetBaseZ());
								cur_field["ride_index"] = static_cast<uint16_t>(rideIndex.ToUnderlying());
								cur_field["ride_type"] = ride->type;
								cur_field["track_dir"] = trackEl->GetDirection();
								if (rtd.HasFlag(RtdFlag::isShopOrFacility))
								{
									cur_field["price"] = ride->price[0];
									
									const auto* rideEntry = ride->getRideEntry();
									void* x{};
								    std::string s = FormatStringIDLegacy(rideEntry->naming.Name, x);
									cur_field["entry_name"] = s;

									event["shops"].append(cur_field);
								}
								else
								{
									event["ride_positions"].append(cur_field);
								}
							}
						
							event["positions"].append(base_field);
						
						} while (TileElementIteratorNext(&iter));
					
						// get number of months for objective
						event["objective_num_months"] = MONTH_COUNT * gameState.scenarioObjective.Year;
						event["objective_num_guests"] = gameState.scenarioObjective.NumGuests;
						event["free_entry"] = gameState.park.Flags & PARK_FLAGS_PARK_FREE_ENTRY;
					
					    Json::StyledWriter styledWriter;
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer(styledWriter.write(event)), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else
					{
						std::cout<<"received in Tick(): "<<request.to_string()<<"\n";
					}
				}
			}
			if (isPaused)
			{
	            if (gDoSingleUpdate && NetworkGetMode() == NETWORK_MODE_NONE)
	            {
	                didRunSingleFrame = true;
	                PauseToggle();
	                numUpdates = 1;
	            }
	            else
	            {
	                // NOTE: Here are a few special cases that would be normally handled in UpdateLogic.
	                // If the game is paused it will not call UpdateLogic at all.
	                numUpdates = 0;

	                if (NetworkGetMode() == NETWORK_MODE_SERVER)
	                {
	                    // Make sure the client always knows about what tick the host is on.
	                    NetworkSendTick();
	                }

	                // Keep updating the money effect even when paused.
	                UpdateMoneyEffect();

	                // Update the animation list. Note this does not
	                // increment the map animation.
	                MapAnimationInvalidateAll();

	                // Post-tick network update
	                NetworkProcessPending();
					gInUpdateCode = true;
	                // Post-tick game actions.
	                GameActions::ProcessQueue();
	                UpdateEntitiesSpatialIndex();
					gInUpdateCode= false;
	            }
			}
        }
		
		if (current_month > -1 || num_ticks > -1)
		{ // run for a month
			int ct = 0;
			while (true)
			{
				ct += 1;
				//std::cout<<"while true\n";
	            gameStateUpdateLogic();
	            if (gameState.scenarioCompletedCompanyValue == kCompanyValueOnFailedObjective)
				{
					//std::cout<<"sending lost\n";
					socket_send.connect(portAddress2);
					socket_send.send(zmq::buffer("lost"), zmq::send_flags::none);
					socket_send.disconnect(portAddress2);

					gGamePaused = true;
				 isPaused = true;
					current_month = -1;
					num_ticks = -1;
					break;
				}
				else if (gameState.scenarioCompletedCompanyValue != kMoney64Undefined)
				{
					//std::cout<<"sending won\n";
					socket_send.connect(portAddress2);
					socket_send.send(zmq::buffer("won"), zmq::send_flags::none);
					socket_send.disconnect(portAddress2);

					gGamePaused = true;
					isPaused = true;
					current_month = -1;
					num_ticks = -1;
					break;
				}
				else
				{
					int32_t month = GetDate().GetMonthsElapsed();
					//std::cout<<num_ticks<< "--"<<ct<< "--"<<current_month<< "--"<<month<< "\n";
					if ((num_ticks > -1 && ct >= num_ticks) || (current_month > -1 && month != current_month))
					{
						//std::cout<<"sending done month\n";
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer("done month"), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);

						gGamePaused = true;
						isPaused = true;
						current_month = -1;
						num_ticks = -1;
						break;
					}
				}
			}
		}
		else
		{
	        // Update the game one or more times
	        for (uint32_t i = 0; i < numUpdates; i++)
	        {
				//std::cout<<"updating\n";
	            gameStateUpdateLogic();
	            if (gGameSpeed == 1)
	            {
	                if (InputGetState() == InputState::Reset || InputGetState() == InputState::Normal)
	                {
	                    if (gInputFlags.has(InputFlag::viewportScrolling))
	                    {
	                        gInputFlags.unset(InputFlag::viewportScrolling);
	                        break;
	                    }
	                }
	                else
	                {
	                    break;
	                }
	            }
	            // Don't call UpdateLogic again if the game was just paused.
	            isPaused |= GameIsPaused();
	            if (isPaused)
	                break;
	        }
		}

        NetworkFlush();

        if (!gOpenRCT2Headless)
        {
            gInputFlags.unset(InputFlag::viewportScrolling);
        }

        // Always perform autosave check, even when paused
        if (gLegacyScene != LegacyScene::titleSequence && gLegacyScene != LegacyScene::trackDesigner
            && gLegacyScene != LegacyScene::trackDesignsManager)
        {
            ScenarioAutosaveCheck();
        }

        if (didRunSingleFrame && GameIsNotPaused() && gLegacyScene != LegacyScene::titleSequence)
        {
            PauseToggle();
        }

        gDoSingleUpdate = false;
    }

    static void gameStateCreateStateSnapshot()
    {
        PROFILED_FUNCTION();

        IGameStateSnapshots* snapshots = GetContext()->GetGameStateSnapshots();

        auto& snapshot = snapshots->CreateSnapshot();
        snapshots->Capture(snapshot);
        snapshots->LinkSnapshot(snapshot, getGameState().currentTicks, ScenarioRandState().s0);
    }

	/*static std::array<CoordsXY, 6> possibleCoords = {
		CoordsXY(6320, 6832),
		CoordsXY(4220, 1350),
		CoordsXY(0, 0),
		CoordsXY(150, 150),
		CoordsXY(200, 200),
		CoordsXY(350, 350)
	};*/

	
    void gameStateUpdateLogic()
    {
	    //const CoordsXY mapCoords = ViewportInteractionGetTileStartAtCursor(screenCoords);
		////std::cout<<mapCoords.x<<","<<mapCoords.y<<"\n";

	    auto& gameState = OpenRCT2::getGameState();
	    //gameState.bankLoan = 0.00_GBP;
		gameState.researchFundingLevel = RESEARCH_FUNDING_MAXIMUM;
        gameState.researchPriorities = EnumsToFlags(ResearchCategory::Gentle, ResearchCategory::Thrill, ResearchCategory::Shop);
		
		if (FinanceGetCurrentCash() <= 30000)
		{ // try to increase, if we have enough money.
			auto remainingLoan = gameState.maxBankLoan - gameState.bankLoan;
			auto moneyToLoan = 30000 < remainingLoan ? 30000 : remainingLoan;
			gameState.bankLoan += moneyToLoan;
			gameState.cash += moneyToLoan;
		}
		else {
			if (gameState.bankLoan > 0)
			{ // pay back until we have 30000 left
				auto moneyToPayBack = gameState.cash - 30000;
				gameState.bankLoan -= moneyToPayBack;
				gameState.cash -= moneyToPayBack;				
			}
		}

		//gameState.maxBankLoan = 1000000;
		/*if (gameState.bankLoan < gameState.maxBankLoan)
		{
			auto diff = gameState.maxBankLoan - gameState.bankLoan;
			gameState.bankLoan = gameState.maxBankLoan;
			gameState.cash += diff;
		}*/
		
		/*if (FinanceGetCurrentCash() <= 10000)
		{ // not enough cash - increase loan
			int diff = 30000 - FinanceGetCurrentCash();
			gameState.bankLoan += diff;
			gameState.cash += diff;
		}
		else if (FinanceGetCurrentCash() > 30000)
		{ // $10,000 -- check if we have loan
			if (gameState.bankLoan > 0)
			{ // set to 30000.
				int diff = FinanceGetCurrentCash() - 30000;
				gameState.bankLoan -= diff;
				gameState.cash -= diff;
			}
		}*/
		
	    // receive a request from client
	    zmq::message_t request;
	    auto num = socket_gs.recv(request, zmq::recv_flags::dontwait);
		if (num > 0)
		{
			Json::Value res;
			Json::Reader reader = {};
			//std::cout<<"received in updatelogic(): "<<request.to_string()<<"\n";
			auto status = reader.parse(request.to_string(), res);
	        if (!status) {
	            //std::cout <<"ConHash:: Error while parsing: " << reader.getFormattedErrorMessages().c_str() << std::endl;
	        } else {
	            ////std::cout<<"Successfully parsed !!" <<std::endl;

				//WindowCloseAll();

				if (res["action"] == "load_park")
				{
					std::string path = res["path"].asString();
					//const char* path_c = path.c_str();
					//std::cout<<"loading\n";
					std::cout<<"Loading(b) " << path<< "\n";
					
				    OpenRCT2::GetContext()->LoadParkFromFile(path, false, true);
					//gGamePaused = true;
					
					/*gameState.maxBankLoan = 1000000;
					if (gameState.bankLoan < gameState.maxBankLoan)
					{
						auto diff = gameState.maxBankLoan - gameState.bankLoan;
						gameState.bankLoan = gameState.maxBankLoan;
						gameState.cash += diff;
					}*/
					
					// set loan to maximum
					/*if (gameState.bankLoan < gameState.maxBankLoan)
					{
						auto diff = gameState.maxBankLoan - gameState.bankLoan;
						gameState.bankLoan = gameState.maxBankLoan;
						gameState.cash += diff;
					}*/
					
					/*auto currentCash = FinanceGetCurrentCash();
					if (currentCash < 200000)
					{
						gameState.bankLoan += (200000-currentCash);
						gameState.cash += (200000-currentCash);
					}*/
					gGamePaused = true;
				}
				else if (res["action"] == "load_track")
				{
					/*
					this.cash = 1000000.00_GBP;
					std::string path = res["path"].asString();
					const char* path_c = path.c_str();

					if (!(createdRideID.IsNull()))
			        {
						auto ride = GetRide(createdRideID);
						//std::cout<<"R1\n";
						createdRideID = RideId::GetNull();

					    // close first...
						auto gameAction1 = RideSetStatusAction(ride->id, RideStatus::closed);
					    //gameAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
					    //});
					    gameAction1.SetFlags(GAME_COMMAND_FLAG_APPLY);

					    GameActions::ExecuteNested(&gameAction1);
						//std::cout<<"R2\n";
					    if (!(ride->lifecycle_flags & RIDE_LIFECYCLE_ON_TRACK))
						{
							ride->lifecycle_flags &= RIDE_LIFECYCLE_ON_TRACK;
						}
					    ride_clear_for_construction(ride);

						auto gameAction2 = RideDemolishAction(ride->id, RIDE_MODIFY_DEMOLISH);
					    gameAction2.SetFlags(GAME_COMMAND_FLAG_APPLY);
					    //gameAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
							//std::cout<<"R3\n";
							//});
						    GameActions::ExecuteNested(&gameAction2);



						    ClearableItems itemsToClear = 0;
				        itemsToClear |= CLEARABLE_ITEMS::SCENERY_SMALL;
				        itemsToClear |= CLEARABLE_ITEMS::SCENERY_LARGE;
				        itemsToClear |= CLEARABLE_ITEMS::SCENERY_FOOTPATH;

							auto mapSizeMaxXY = GetMapSizeMaxXY();
						    auto range = MapRange(0, 0, mapSizeMaxXY.x, mapSizeMaxXY.y);

						    auto cAction = ClearAction(range, itemsToClear);
							auto res = GameActions::Execute(&cAction);

							//ride_action_modify(&ride, RIDE_MODIFY_DEMOLISH, GAME_COMMAND_FLAG_APPLY);
				        }

					    std::unique_ptr<TrackDesign> _trackDesign = TrackDesignImport(path_c);
						if (_trackDesign != nullptr)
						{
							//_trackDesign->name = "Test";

							RideId _rideIndex{ RideId::GetNull() };

							auto _currentTrackPieceDirection = static_cast<Direction>(0);


							CoordsXYZ trackLoc;
							GameActions::Result res;
							bool found2 = false;
							for (auto &mapCoords : possibleCoords)
							{
							    auto surfaceElement = MapGetSurfaceElementAt(mapCoords);
							    auto mapZ = surfaceElement->GetBaseZ() + TrackDesignGetZPlacement(_trackDesign.get(), GetOrAllocateRide(_rideIndex), { mapCoords, surfaceElement->GetBaseZ() });
								////std::cout<<"mapz:"<<mapZ<<"\n";

							    trackLoc = { mapCoords, mapZ };
								bool found = false;
							    for (int32_t i2 = 0; i2 < 7; i2++, trackLoc.z += 8)
							    {
							        auto tdAction = TrackDesignAction(CoordsXYZD{ trackLoc.x, trackLoc.y, trackLoc.z, _currentTrackPieceDirection }, *_trackDesign);
							        tdAction.SetFlags(0);
							        res = GameActions::Query(&tdAction);

							        // If successful don't keep trying.
							        // If failure due to no money then increasing height only makes problem worse
							        if (res.Error != GameActions::Status::Ok) // || res.Error == GameActions::Status::InsufficientFunds)
							        {
										//std::cout<<"ERR1\n" << res.GetErrorMessage()<<"\n";
							        }
									else
									{
										found = true;
										break;
									}
							    }
								if (found)
								{
									found2 = true;
									break;
								}
							}

							if (!found2)
							{
								//std::cout<<"stopping\n";
								return;
							}
							//std::cout<<"Placing\n";
						    auto tdAction = TrackDesignAction({ trackLoc, _currentTrackPieceDirection }, *_trackDesign);
						    tdAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
						        if (result->Error == GameActions::Status::Ok)
						        {
					            auto rideId = result->GetData<RideId>();
					            auto getRide = get_ride(rideId);
									createdRideID = rideId;
					            if (getRide != nullptr)
					            {
					                //auto intent = Intent(WC_RIDE);
					                //intent.putExtra(INTENT_EXTRA_RIDE_ID, rideId.ToUnderlying());
					                //context_open_intent(&intent);

									    RideSetStatusAction gameAction = RideSetStatusAction(rideId, RideStatus::open);
										gameAction.SetCallback([&](const GameAction*, const GameActions::Result* result) {
											//std::cout<<"CALLBACK\n";
											//std::cout<<result->GetErrorMessage()<<"\n";
										});
									    GameActions::ExecuteNested(&gameAction);
						            }
						        }
						        else
						        {
									//std::cout<<"ERR2\n";
								}
						    });
						    res = GameActions::Execute(&tdAction);

						    // send the reply to the client
							////std::cout << "Sending back.\n";
						    //socket.send(zmq::buffer(data), zmq::send_flags::none);
						}
						*/
					}
					else if (res["action"] == "load_park_json")
					{
						std::string path = res["path"].asString();
						//const char* path_c = path.c_str();

						OpenRCT2::GetContext()->LoadParkFromFile("/Users/jcampbell/Library/Application Support/OpenRCT2/scenario/My new scenario.park", false, true);
					    OpenRCT2::GetContext()->LoadParkFromFile(path, false, true);
					}
					else if (res["action"] == "pause")
					{
						gGamePaused = true;
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer("done"), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
						current_month = -1;
						num_ticks = -1;
					}
					else if (res["action"] == "unpause")
					{
						gGamePaused = false;
						socket_send.connect(portAddress2);
						socket_send.send(zmq::buffer("done"), zmq::send_flags::none);
						socket_send.disconnect(portAddress2);
					}
					else
					{
						std::cout<<"received in updatelogic: " << res["action"] << "\n";
					}
	        }
		}
		else
		{
			if (!(createdRideID.IsNull()))
	        {
				auto ride = GetRide(createdRideID);
				if (ride->customName == "Test done")
				{
					auto gameAction1 = RideSetStatusAction(ride->id, RideStatus::closed);
				    gameAction1.SetFlags(GAME_COMMAND_FLAG_APPLY);			
				    GameActions::ExecuteNested(&gameAction1);
					ride->customName = "Test done2";
				}
			}
		}

		if ((num_ticks > -1 || current_month > -1) && visitCounts)
		{
			for (auto* peep : EntityList<Guest>())
			{
				CoordsXYZ pos = peep->GetLocation();
				if (pos.x < 0 || pos.y < 0 || pos.x >= gameState.mapSize.x*32 || pos.y >= gameState.mapSize.y*32)
					continue;
				if (!MapIsLocationOwnedOrHasRights(CoordsXY{ pos.x , pos.y }))
				{
					continue;
				}
				
				uint32_t px, py;
				px = static_cast<int>(pos.x/32);
				py = static_cast<int>(pos.y/32);
				//std::cout << px <<","<< py << "\n";
				visitCounts[px][py] += 1;
				//std::cout<< visitCounts[px][py]<<"\n";
			}
		}
		
		/*if (num_ticks > -1)
		{ // running simulation
			num_ticks --;
			
			if (num_ticks == 0)
			{
				socket_send.connect(portAddress2);
				socket_send.send(zmq::buffer("done"), zmq::send_flags::none);
				socket_send.disconnect(portAddress2);
				//current_month = -1;
				num_ticks = -1;
				//gGamePaused = true;
			}
		}*/
		
		
        PROFILED_FUNCTION();

        gInUpdateCode = true;

        gScreenAge++;
        if (gScreenAge == 0)
            gScreenAge--;

        GetContext()->GetReplayManager()->Update();

        NetworkUpdate();

        //auto& gameState = getGameState();

        if (NetworkGetMode() == NETWORK_MODE_SERVER)
        {
            if (NetworkGamestateSnapshotsEnabled())
            {
                gameStateCreateStateSnapshot();
            }

            // Send current tick out.
            NetworkSendTick();
        }
        else if (NetworkGetMode() == NETWORK_MODE_CLIENT)
        {
            // Don't run past the server, this condition can happen during map changes.
            if (NetworkGetServerTick() == gameState.currentTicks)
            {
                gInUpdateCode = false;
                return;
            }

            // Check desync.
            bool desynced = NetworkCheckDesynchronisation();
            if (desynced)
            {
                // If desync debugging is enabled and we are still connected request the specific game state from server.
                if (NetworkGamestateSnapshotsEnabled() && NetworkGetStatus() == NETWORK_STATUS_CONNECTED)
                {
                    // Create snapshot from this tick so we can compare it later
                    // as we won't pause the game on this event.
                    gameStateCreateStateSnapshot();

                    NetworkRequestGamestateSnapshot();
                }
            }
        }

#ifdef ENABLE_SCRIPTING
        // Stash the current day number before updating the date so that we
        // know if the day number changes on this tick.
        auto day = gameState.date.GetDay();
#endif

        DateUpdate(gameState);

        ScenarioUpdate(gameState);
        ClimateUpdate();
        MapUpdateTiles();

        // Temporarily remove provisional paths to prevent peep from interacting with them
        auto removeProvisionalIntent = Intent(INTENT_ACTION_REMOVE_PROVISIONAL_ELEMENTS);
        ContextBroadcastIntent(&removeProvisionalIntent);

        MapUpdatePathWideFlags();
        PeepUpdateAll();
        auto restoreProvisionalIntent = Intent(INTENT_ACTION_RESTORE_PROVISIONAL_ELEMENTS);
        ContextBroadcastIntent(&restoreProvisionalIntent);
        VehicleUpdateAll();
        UpdateAllMiscEntities();
        Ride::updateAll();

        if (!isInEditorMode())
        {
            Park::Update(gameState, gameState.date);
        }

        ResearchUpdate();
        RideRatingsUpdateAll();
        RideMeasurementsUpdate();
        News::UpdateCurrentItem();

        MapAnimationInvalidateAll();
        VehicleSoundsUpdate();
        PeepUpdateCrowdNoise();
        ClimateUpdateSound();
        EditorOpenWindowsForCurrentStep();

        // Update windows
        // WindowDispatchUpdateAll();

        UpdateEntitiesSpatialIndex();

        // Start autosave timer after update
        if (gLastAutoSaveUpdate == kAutosavePause)
        {
            gLastAutoSaveUpdate = Platform::GetTicks();
        }

        GameActions::ProcessQueue();

        NetworkProcessPending();
        NetworkFlush();

        gameState.currentTicks++;

#ifdef ENABLE_SCRIPTING
        auto& hookEngine = GetContext()->GetScriptEngine().GetHookEngine();
        hookEngine.Call(HookType::intervalTick, true);

        if (day != gameState.date.GetDay())
        {
            hookEngine.Call(HookType::intervalDay, true);
        }
#endif

        gInUpdateCode = false;
    }
} // namespace OpenRCT2
