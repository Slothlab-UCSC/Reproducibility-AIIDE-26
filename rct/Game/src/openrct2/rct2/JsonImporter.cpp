/*****************************************************************************
 * Copyright (c) 2014-2020 OpenRCT2 developers
 *
 * For a complete list of all authors, please refer to contributors.md
 * Interested in contributing? Visit https://github.com/OpenRCT2/OpenRCT2
 *
 * OpenRCT2 is licensed under the GNU General Public License version 3.
 *****************************************************************************/

#include "../Context.h"
#include "../Diagnostic.h"
#include "../Editor.h"
#include "../Game.h"
#include "../GameState.h"
#include "../OpenRCT2.h"
#include "../ParkImporter.h"
#include "../core/Console.hpp"
#include "../core/EnumUtils.hpp"
#include "../core/FileStream.h"
#include "../core/IStream.hpp"
#include "../core/MemoryStream.h"
#include "../core/Numerics.hpp"
#include "../core/Path.hpp"
#include "../core/Random.hpp"
#include "../core/SawyerCoding.h"
#include "../core/String.hpp"
#include "../entity/Balloon.h"
#include "../entity/Duck.h"
#include "../entity/EntityList.h"
#include "../entity/EntityRegistry.h"
#include "../entity/EntityTweener.h"
#include "../entity/Fountain.h"
#include "../entity/Guest.h"
#include "../entity/Litter.h"
#include "../entity/MoneyEffect.h"
#include "../entity/Particle.h"
#include "../entity/PatrolArea.h"
#include "../entity/Staff.h"
#include "../interface/Viewport.h"
#include "../localisation/Formatting.h"
#include "../management/Award.h"
#include "../management/Finance.h"
#include "../management/Marketing.h"
#include "../management/NewsItem.h"
#include "../management/Research.h"
#include "../network/Network.h"
#include "../object/LargeSceneryEntry.h"
#include "../object/ObjectLimits.h"
#include "../object/ObjectList.h"
#include "../object/ObjectManager.h"
#include "../object/ObjectRepository.h"
#include "../object/ScenarioTextObject.h"
#include "../object/WallSceneryEntry.h"
#include "../park/Legacy.h"
#include "../park/ParkPreview.h"
#include "../peep/RideUseSystem.h"
#include "../rct12/CSStringConverter.h"
#include "../rct12/EntryList.h"
#include "../rct12/RCT12.h"
#include "../rct12/SawyerChunkReader.h"
#include "../rct12/ScenarioPatcher.h"
#include "../rct2/RCT2.h"
#include "../ride/Ride.h"
#include "../ride/RideData.h"
#include "../ride/RideRatings.h"
#include "../ride/ShopItem.h"
#include "../ride/Station.h"
#include "../ride/Track.h"
#include "../ride/TrainManager.h"
#include "../ride/Vehicle.h"
#include "../scenario/ScenarioRepository.h"
#include "../scenario/ScenarioSources.h"
#include "../world/Climate.h"
#include "../world/Entrance.h"
#include "../world/MapAnimation.h"
#include "../world/Park.h"
#include "../world/Scenery.h"
#include "../world/TilePointerIndex.hpp"
#include "../world/tile_element/BannerElement.h"
#include "../world/tile_element/EntranceElement.h"
#include "../world/tile_element/LargeSceneryElement.h"
#include "../world/tile_element/PathElement.h"
#include "../world/tile_element/SmallSceneryElement.h"
#include "../world/tile_element/SurfaceElement.h"
#include "../world/tile_element/TileElement.h"
#include "../world/tile_element/TrackElement.h"
#include "../world/tile_element/WallElement.h"

#include "../json/json.h"

#include <cassert>
#include <mutex>
#include <fstream>
#include <algorithm>

using namespace OpenRCT2;

namespace OpenRCT2::RCT2
{
#define DECRYPT_MONEY(money) (static_cast<money32>(Numerics::rol32((money) ^ 0xF4EC9621, 13)))

    static std::mutex mtx;

    /**
     * Class to import JSON saved games.
     */
    class JsonImporter final : public IParkImporter
    {
    private:
        IObjectRepository& _objectRepository;

		u8string _s6Path;
        S6Data _s6{};
		Json::Value _json;
        uint8_t _gameVersion = 0;
        bool _isSV7 = false;
        OpenRCT2::BitSet<Limits::kMaxRidesInPark> _isFlatRide{};
        ObjectEntryIndex _pathToSurfaceMap[16];
        ObjectEntryIndex _pathToQueueSurfaceMap[16];
        ObjectEntryIndex _pathToRailingMap[16];
        RCT12::EntryList _terrainSurfaceEntries;
        RCT12::EntryList _terrainEdgeEntries;

    public:
        JsonImporter(IObjectRepository& objectRepository)
            : _objectRepository(objectRepository)
        {
        }

        ParkLoadResult Load(const u8string& path, bool skipObjectCheck = false) override
        {
            const auto extension = Path::GetExtension(path);
            return LoadSavedGame(path);
        }

        ParkLoadResult LoadSavedGame(const u8string& path, bool skipObjectCheck = false) override
        {
            auto fs = OpenRCT2::FileStream(path, OpenRCT2::FileMode::open);
            auto result = LoadFromStream(&fs, false, skipObjectCheck);
            _s6Path = path.c_str();
            return result;
        }

        ParkLoadResult LoadScenario(const u8string& path, bool skipObjectCheck = false) override
        {
            throw std::runtime_error("can't load scenario.");
        }

        ParkLoadResult LoadFromStream(
            OpenRCT2::IStream* stream, bool isScenario, [[maybe_unused]] bool skipObjectCheck = false,
	        const u8string& path = {}) override
        {
		    std::ifstream f(path);
			f >> _json;
			
            //for (uint16_t i = 0; i < _s6.header.num_packed_objects; i++)
            //    _objectRepository.ExportPackedObject(stream);// Read packed objects
			
            //chunkReader.ReadChunk(&_s6.Objects, sizeof(_s6.Objects));
            //chunkReader.ReadChunk(&_s6.tile_elements, sizeof(_s6.tile_elements));
			
			
			
            return ParkLoadResult(GetRequiredObjects());
        }

        bool GetDetails(ScenarioIndexEntry* dst)
        {
            *dst = {};
            return false;
        }

        bool PopulateIndexEntry(ScenarioIndexEntry* dst) override
        {
            *dst = {};

            dst->Category = _s6.Info.Category;
            dst->ObjectiveType = _s6.Info.ObjectiveType;
            dst->ObjectiveArg1 = _s6.Info.ObjectiveArg1;
            dst->ObjectiveArg2 = _s6.Info.ObjectiveArg2;
            dst->ObjectiveArg3 = _s6.Info.ObjectiveArg3;
            dst->Highscore = nullptr;

            if (String::isNullOrEmpty(_s6.Info.Name))
            {
                // If the scenario doesn't have a name, set it to the filename
                dst->Name = Path::GetFileNameWithoutExtension(dst->Path);
            }
            else
            {
                // Normalise the name to make the scenario as recognisable as possible.
                dst->Name = ScenarioSources::NormaliseName(_s6.Info.Name);
            }

            // Look up and store information regarding the origins of this scenario.
            SourceDescriptor desc;
            if (ScenarioSources::TryGetByName(dst->Name.c_str(), &desc))
            {
                dst->ScenarioId = desc.id;
                dst->SourceIndex = desc.index;
                dst->SourceGame = ScenarioSource{ desc.source };
                dst->Category = desc.category;
            }
            else
            {
                dst->ScenarioId = SC_UNIDENTIFIED;
                dst->SourceIndex = -1;
                if (dst->Category == ScenarioCategory::real)
                {
                    dst->SourceGame = ScenarioSource::Real;
                }
                else
                {
                    dst->SourceGame = ScenarioSource::Other;
                }
            }

            // dst->name will be translated later so keep the untranslated name here
            dst->InternalName = dst->Name;
            dst->Details = _s6.Info.Details;

            if (!desc.textObjectId.empty())
            {
                auto& objManager = GetContext()->GetObjectManager();

                // Ensure only one thread talks to the object manager at a time
                std::lock_guard lock(mtx);

                // Unload loaded scenario text object, if any.
                if (auto* obj = objManager.GetLoadedObject<ScenarioTextObject>(0); obj != nullptr)
                    objManager.UnloadObjects({ obj->GetDescriptor() });

                // Load the one specified
                if (auto* obj = objManager.LoadObject(desc.textObjectId); obj != nullptr)
                {
                    auto* textObject = reinterpret_cast<ScenarioTextObject*>(obj);
                    dst->Name = textObject->GetScenarioName();
                    dst->Details = textObject->GetScenarioDetails();
                }
            }

            return true;
        }

        ParkPreview GetParkPreview() override
        {
            return {};
        }

        void Import(GameState_t& gameState) override
        {
            Initialise();

            /*gEditorStep = _s6.info.editor_step;
            gScenarioCategory = static_cast<SCENARIO_CATEGORY>(_s6.info.category);

            // Some scenarios have their scenario details in UTF-8, due to earlier bugs in OpenRCT2.
            auto loadMaybeUTF8 = [](std::string_view str) -> std::string {
                return !IsLikelyUTF8(str) ? rct2_to_utf8(str, RCT2LanguageId::EnglishUK) : std::string(str);
            };

            if (_s6.header.type == S6_TYPE_SCENARIO)
            {
                gscenarioName = loadMaybeUTF8(_s6.info.name);
                gscenarioDetails = loadMaybeUTF8(_s6.info.details);
            }
            else
            {
                // Saved games do not have an info chunk
                gscenarioName = loadMaybeUTF8(_s6.scenario_name);
                gscenarioDetails = loadMaybeUTF8(_s6.scenario_description);
            }

            gDateMonthsElapsed = static_cast<int32_t>(_s6.elapsed_months);
            gDateMonthTicks = _s6.current_day;
            gCurrentTicks = _s6.game_ticks_1;

            scenario_rand_seed(_s6.scenario_srand_0, _s6.scenario_srand_1);*/

            //DetermineFlatRideStatus();
			std::cout<<"tile\n";
            ImportTileElements();
            //ImportEntities();
			std::cout<<"done tile\n";
            /*gInitialCash = ToMoney64(_s6.initial_cash);
            gBankLoan = ToMoney64(_s6.current_loan);

            gParkFlags = _s6.park_flags & ~PARK_FLAGS_NO_MONEY_SCENARIO;

            // RCT2 used a different flag for `no money` when the park is a scenario
            if (_s6.header.type == S6_TYPE_SCENARIO)
            {
                if (_s6.park_flags & PARK_FLAGS_NO_MONEY_SCENARIO)
                    gParkFlags |= PARK_FLAGS_NO_MONEY;
                else
                    gParkFlags &= ~PARK_FLAGS_NO_MONEY;
            }

            gParkEntranceFee = _s6.park_entrance_fee;
            // rct1_park_entrance_x
            // rct1_park_entrance_y
            // pad_013573EE
            // rct1_park_entrance_z */

			std::cout<<"peep\n";
            ImportpeepSpawns();
			std::cout<<"done peep\n";

            /*gGuestChangeModifier = _s6.guest_count_change_modifier;
            gResearchFundingLevel = _s6.current_research_level;
            // pad_01357400
            // _s6.researched_track_types_a
            // _s6.researched_track_types_b

            gNumGuestsInPark = _s6.guests_in_park;
            gNumGuestsHeadingForPark = _s6.guests_heading_for_park;

            for (size_t i = 0; i < Limits::ExpenditureTableMonthCount; i++)
            {
                for (size_t j = 0; j < Limits::ExpenditureTypeCount; j++)
                {
                    gExpenditureTable[i][j] = ToMoney64(_s6.expenditure_table[i][j]);
                }
            }

            gNumGuestsInParkLastWeek = _s6.last_guests_in_park;
            // pad_01357BCA
            gStaffHandymanColour = _s6.handyman_colour;
            gStaffMechanicColour = _s6.mechanic_colour;
            gStaffSecurityColour = _s6.security_colour;

            gParkRating = _s6.park_rating;
			*/
			
            auto& park = gameState.park; //GetPark();
            Park::ResetHistories(gameState);
            /*std::copy(std::begin(_s6.park_rating_history), std::end(_s6.park_rating_history), gParkRatingHistory);
            for (size_t i = 0; i < std::size(_s6.guests_in_park_history); i++)
            {
                if (_s6.guests_in_park_history[i] != RCT12ParkHistoryUndefined)
                {
                    gGuestsInParkHistory[i] = _s6.guests_in_park_history[i] * RCT12GuestsInParkHistoryFactor;
                }
            }

            gResearchPriorities = _s6.active_research_types;
            gResearchProgressStage = _s6.research_progress_stage;
            if (_s6.last_researched_item_subject != RCT12_RESEARCHED_ITEMS_SEPARATOR)
                gResearchLastItem = RCT12ResearchItem{ _s6.last_researched_item_subject,
                                                       EnumValue(ResearchCategory::Transport) }
                                        .ToResearchItem();
            else
                gResearchLastItem = std::nullopt;
            // pad_01357CF8
            if (_s6.next_research_item != RCT12_RESEARCHED_ITEMS_SEPARATOR)
                gResearchNextItem = RCT12ResearchItem{ _s6.next_research_item, _s6.next_research_category }.ToResearchItem();
            else
                gResearchNextItem = std::nullopt;

            gResearchProgress = _s6.research_progress;
            gResearchExpectedDay = _s6.next_research_expected_day;
            gResearchExpectedMonth = _s6.next_research_expected_month;
            gGuestInitialHappiness = _s6.guest_initial_happiness;
			*/
            gameState.park.Size = _json["park_size"].asUInt(); //_s6.park_size;
            /*
			_guestGenerationProbability = _s6.guest_generation_probability;
            gTotalRideValueForMoney = _s6.total_ride_value_for_money;
            gMaxBankLoan = ToMoney64(_s6.maximum_loan);
            gGuestInitialCash = _s6.guest_initial_cash;
            gGuestInitialHunger = _s6.guest_initial_hunger;
            gGuestInitialThirst = _s6.guest_initial_thirst;
            gScenarioObjective.Type = _s6.objective_type;
            gScenarioObjective.Year = _s6.objective_year;
            // pad_013580FA
            gScenarioObjective.Currency = _s6.objective_currency;
            // In RCT2, the ride string IDs start at index STR_0002 and are directly mappable.
            // This is not always the case in OpenRCT2, so we use the actual ride ID.
            if (gScenarioObjective.Type == OBJECTIVE_BUILD_THE_BEST)
                gScenarioObjective.RideId = _s6.objective_guests - RCT2_RIDE_STRING_START;
            else
                gScenarioObjective.NumGuests = _s6.objective_guests;
            ImportmarketingCampaigns();

            gCurrentExpenditure = ToMoney64(_s6.current_expenditure);
            gCurrentProfit = ToMoney64(_s6.current_profit);
            gWeeklyProfitAverageDividend = ToMoney64(_s6.weekly_profit_average_dividend);
            gWeeklyProfitAverageDivisor = _s6.weekly_profit_average_divisor;
            // pad_0135833A

            gParkValue = ToMoney64(_s6.park_value);

            for (size_t i = 0; i < Limits::FinanceGraphSize; i++)
            {
                gCashHistory[i] = ToMoney64(_s6.balance_history[i]);
                gWeeklyProfitHistory[i] = ToMoney64(_s6.weekly_profit_history[i]);
                gParkValueHistory[i] = ToMoney64(_s6.park_value_history[i]);
            }

            gScenarioCompletedCompanyValue = RCT12CompletedCompanyValueToOpenRCT2(_s6.completed_company_value);
            gTotalAdmissions = _s6.total_admissions;
            gTotalIncomeFromAdmissions = ToMoney64(_s6.income_from_admissions);
            gCompanyValue = ToMoney64(_s6.company_value);
            std::memcpy(gPeepWarningThrottle, _s6.peep_warning_throttle, sizeof(_s6.peep_warning_throttle));

            // Awards
            auto& awards = GetAwards();
            for (auto& src : _s6.awards)
            {
                if (src.time != 0)
                {
                    awards.push_back(Award{ src.time, static_cast<AwardType>(src.type) });
                }
            }

            gLandPrice = _s6.land_price;
            gConstructionRightsPrice = _s6.construction_rights_price;
            // unk_01358774
            // pad_01358776
            // _s6.cd_key
            _gameVersion = _s6.game_version_number;
            gScenarioCompanyValueRecord = _s6.completed_company_value_record;
            // _s6.loan_hash;
            // pad_013587CA
            gHistoricalProfit = ToMoney64(_s6.historical_profit);
            // pad_013587D4
            gscenarioCompletedBy = std::string_view(_s6.scenario_completed_name, sizeof(_s6.scenario_completed_name));
            gCash = ToMoney64(DECRYPT_MONEY(_s6.cash));
            // pad_013587FC
            gParkRatingCasualtyPenalty = _s6.park_rating_casualty_penalty;
			*/
			
			std::cout<<"e1"<<std::endl;
            gameState.mapSize = {_json["map_size"]["x"].asInt(), _json["map_size"]["y"].asInt() }; // _s6.map_size, _s6.map_size };
			std::cout<<"e1-2"<<std::endl;
			/*
            gSamePriceThroughoutPark = _s6.same_price_throughout
                | (static_cast<uint64_t>(_s6.same_price_throughout_extended) << 32);
            _suggestedGuestMaximum = _s6.suggested_max_guests;
            gScenarioParkRatingWarningDays = _s6.park_rating_warning_days;
            gLastEntranceStyle = _s6.last_entrance_style;
            // rct1_water_colour
            // pad_01358842
            ImportResearchList();
			*/
            //gMapBaseZ = 7; // _s6.map_base_z;
            //gBankLoanInterestRate = _s6.current_interest_rate;
            // pad_0135934B
            // Preserve compatibility with vanilla RCT2's save format.
            gameState.park.Entrances.clear();

			
			std::cout<<"e2"<<std::endl;
			
			for (unsigned int i = 0; i < _json["entrances"].size(); i ++)
			{
				Json::Value spawn_j = _json["entrances"][i];
                CoordsXYZD spawn = { spawn_j["x"].asInt(), spawn_j["y"].asInt(), spawn_j["z"].asInt(), static_cast<Direction>(spawn_j["direction"].asUInt()) };
                gameState.park.Entrances.push_back(spawn);
			}
			std::cout<<"e2-2"<<std::endl;
			
			/*
            for (uint8_t i = 0; i < Limits::MaxParkEntrances; i++)
            {
                if (_s6.park_entrance_x[i] != LOCATION_NULL)
                {
                    CoordsXYZD entrance;
                    entrance.x = _s6.park_entrance_x[i];
                    entrance.y = _s6.park_entrance_y[i];
                    entrance.z = _s6.park_entrance_z[i];
                    entrance.direction = _s6.park_entrance_direction[i];
                    gParkEntrances.push_back(entrance);
                }
            }*/
			
			/*
            if (_s6.header.type == S6_TYPE_SCENARIO)
            {
                // _s6.scenario_filename is wrong for some RCT2 expansion scenarios, so we use the real filename
                gScenarioSavePath = Path::GetFileName(_s6Path);
            }
            else
            {
                // For savegames the filename can be arbitrary, so we have no choice but to rely on the name provided
                gScenarioSavePath = std::string(String::ToStringView(_s6.scenario_filename, std::size(_s6.scenario_filename)));
            }
            gCurrentRealTimeTicks = 0;
			*/
			
            ImportRides();
			
			/*
            gSavedAge = _s6.saved_age;
            gSavedView = ScreenCoordsXY{ _s6.saved_view_x, _s6.saved_view_y };
            gSavedViewZoom = ZoomLevel{ static_cast<int8_t>(_s6.saved_view_zoom) };
            gSavedViewRotation = _s6.saved_view_rotation;

            ImportRideRatingsCalcData();
            ImportRideMeasurements();
            gNextGuestNumber = _s6.next_guest_index;
            gGrassSceneryTileLoopPosition = _s6.grass_and_scenery_tilepos;
            // unk_13CA73E
            // pad_13CA73F
            // unk_13CA740
            gClimate = ClimateType{ _s6.climate };
            // pad_13CA741;
            // byte_13CA742
            // pad_013CA747
            gClimateUpdateTimer = _s6.climate_update_timer;
            gClimateCurrent.Weather = WeatherType{ _s6.current_weather };
            gClimateNext.Weather = WeatherType{ _s6.next_weather };
            gClimateCurrent.Temperature = _s6.temperature;
            gClimateNext.Temperature = _s6.next_temperature;
            gClimateCurrent.WeatherEffect = WeatherEffectType{ _s6.current_weather_effect };
            gClimateNext.WeatherEffect = WeatherEffectType{ _s6.next_weather_effect };
            gClimateCurrent.WeatherGloom = _s6.current_weather_gloom;
            gClimateNext.WeatherGloom = _s6.next_weather_gloom;
            gClimateCurrent.Level = static_cast<WeatherLevel>(_s6.current_weather_level);
            gClimateNext.Level = static_cast<WeatherLevel>(_s6.next_weather_level);

            // News items
            News::InitQueue();
            for (size_t i = 0; i < Limits::MaxNewsItems; i++)
            {
                const rct12_news_item* src = &_s6.news_items[i];
                News::Item* dst = &gNewsItems[i];
                if (src->type < News::ItemTypeCount)
                {
                    dst->Type = static_cast<News::ItemType>(src->type);
                    dst->Flags = src->Flags;
                    dst->Assoc = src->Assoc;
                    dst->Ticks = src->Ticks;
                    dst->MonthYear = src->MonthYear;
                    dst->Day = src->Day;
                    dst->Text = ConvertFormattedStringToOpenRCT2(std::string_view(src->Text, sizeof(src->Text)));
                }
                else
                {
                    // In case where news item type is broken, consider all remaining news items invalid.
                    log_error("Invalid news type 0x%x for news item %d, ignoring remaining news items", src->type, i);
                    // Still need to set the correct type to properly terminate the queue
                    dst->Type = News::ItemType::Null;
                    break;
                }
            }

            // pad_13CE730
            // rct1_scenario_flags
            gWidePathTileLoopPosition.x = _s6.wide_path_tile_loop_x;
            gWidePathTileLoopPosition.y = _s6.wide_path_tile_loop_y;
            // pad_13CE778
			*/
			
            // Fix and set dynamic variables
            MapStripGhostFlagFromElements();
            //ConvertScenarioStringsToUTF8();
            MapCountRemainingLandRights();
            DetermineRideEntranceAndExitLocations();

            park.Name = "Test"; //GetUserString(_s6.park_name);

            /*if (_isScenario)
            {
                OpenRCT2::RCT12::FetchAndApplyScenarioPatch(_s6Path);
            }*/

            ResearchDetermineFirstOfType();
            UpdateConsolidatedPatrolAreas();

            CheatsReset();
            ClearRestrictedScenery();
			std::cout<<"done import\n";
        }

        void AddDefaultEntries()
        {
            // Add default surfaces
            _terrainSurfaceEntries.AddRange(DefaultTerrainSurfaces);

            // Add default edges
            _terrainEdgeEntries.AddRange(DefaultTerrainEdges);
        }

        void ConvertScenarioStringsToUTF8(GameState_t& gameState)
        {
            // Scenario details
            gameState.scenarioCompletedBy = RCT2StringToUTF8(gameState.scenarioCompletedBy, RCT2LanguageId::EnglishUK);
            gameState.scenarioName = RCT2StringToUTF8(gameState.scenarioName, RCT2LanguageId::EnglishUK);
            gameState.scenarioDetails = RCT2StringToUTF8(gameState.scenarioDetails, RCT2LanguageId::EnglishUK);
        }

        void ImportRides()
        {
			//int index = 0;
			for (unsigned int i = 0; i < _json["rides"].size(); i ++)
			{
				Json::Value ride_j = _json["rides"][i];			
                const auto rideId = RideId::FromUnderlying(i);
				//index += 1;
                auto dst = RideAllocateAtIndex(rideId);
                ImportRide(dst, ride_j, rideId);
				
			}
			/*	
            for (uint8_t index = 0; index < Limits::MaxRidesInPark; index++)
            {
                auto src = &_s6.rides[index];
                if (src->type != kRideTypeNull)
                {
                    const auto rideId = RideId::FromUnderlying(index);
                    auto dst = GetOrAllocateRide(rideId);
                    ImportRide(dst, src, rideId);
                }
            }*/
        }

       /**
        * This code is needed to detect hacks where a tracked ride has been made invisible
        * by setting its ride type to a flat ride.
        *
        * The function should classify rides as follows:
        * 1. If the ride type is tracked and its vehicles also belong on tracks, it should be classified as tracked.
        * 2. If the ride type is a flat ride, but its vehicles belong on tracks,
        *     it should be classified as tracked (Crooked House mod).
        * 3. If the ride type is tracked and its vehicles belong to a flat ride, it should be classified as tracked.
        * 4. If the ride type is a flat ride and its vehicles also belong to a flat ride, it should be classified as a flat
        * ride.
        */
       void DetermineFlatRideStatus()
       {
           for (uint8_t index = 0; index < Limits::kMaxRidesInPark; index++)
           {
               auto src = &_s6.Rides[index];
               if (src->type == kRideTypeNull)
                   continue;

               auto subtype = RCTEntryIndexToOpenRCT2EntryIndex(src->subtype);
               auto* rideEntry = GetRideEntryByIndex(subtype);
               // If the ride is tracked, we don’t need to check the vehicle any more.
               if (!GetRideTypeDescriptor(src->type).HasFlag(RtdFlag::isFlatRide))
               {
                   _isFlatRide[index] = false;
                   continue;
               }

               // We have established the ride type is a flat ride, which means the vehicle now determines whether it is a
               // true flat ride (scenario 4) or a tracked ride with an invisibility hack (scenario 2).
               ObjectEntryIndex originalRideType = src->type;
               if (rideEntry != nullptr)
               {
                   originalRideType = rideEntry->GetFirstNonNullRideType();
               }
               const auto isFlatRide = GetRideTypeDescriptor(originalRideType).HasFlag(RtdFlag::isFlatRide);
               _isFlatRide.set(static_cast<size_t>(index), isFlatRide);
           }
       }

       bool IsFlatRide(const uint8_t rct12RideIndex)
       {
           if (rct12RideIndex == kRCT12RideIdNull)
               return false;
           return _isFlatRide[rct12RideIndex];
       }

        void ImportRide(::Ride* dst, Json::Value src, const RideId rideIndex)
        {
            *dst = {};
            dst->id = rideIndex;

            //auto subtype = src["subtype"].asUInt(); // RCTEntryIndexToOpenRCT2EntryIndex(src->subtype);
            /*if (RCT2RideTypeNeedsConversion(src->type))
            {
                auto* rideEntry = get_ride_entry(subtype);
                if (rideEntry != nullptr)
                {
                    rideType = RCT2RideTypeToOpenRCT2RideType(src->type, rideEntry);
                }
            }*/

            ObjectEntryIndex rideType = src["type"].asUInt();
            if (rideType >= RIDE_TYPE_COUNT)
            {
                //log_error("Invalid ride type for a ride in this save.");
                throw UnsupportedRideTypeException(rideType);
            }
            dst->type = rideType;

			auto identifier = src["subtype_obj_id"].asString();
		    auto& objectMgr = OpenRCT2::GetContext()->GetObjectManager();
			auto entryIndex = objectMgr.GetLoadedObjectEntryIndex(identifier); //subtype;
			if (entryIndex == kObjectEntryIndexNull)
			{
				std::cout << "could not find this subtype <"<<identifier<<">\n";
			}
			dst->subtype = entryIndex;
			            
			dst->mode = static_cast<RideMode>(src["mode"].asUInt());
            
			/*dst->colour_scheme_type = src->colour_scheme_type;

            for (uint8_t i = 0; i < Limits::MaxTrainsPerRide; i++)
            {
                dst->vehicle_colours[i].Body = src->vehicle_colours[i].body_colour;
                dst->vehicle_colours[i].Trim = src->vehicle_colours[i].trim_colour;
            }*/

            // pad_046;
            dst->status = RideStatus::open; //static_cast<RideStatus>(src->status);

            //dst->default_name_number = src->name_arguments_number;
            dst->customName = src["name"].asString();
			/*if (is_user_string_id(src->name))
            {
                dst->customName = GetUserString(src->name);
            }
            else
            {
                dst->default_name_number = src->name_arguments_number;
            }

            if (src->overallView.IsNull())
            {*/
                dst->overallView.SetNull();
				/*}
            else
            {
                auto tileLoc = TileCoordsXY(src->overallView.x, src->overallView.y);
                dst->overallView = tileLoc.ToCoordsXY();
            }*/

            for (StationIndex::UnderlyingType i = 0; i < Limits::kMaxStationsPerRide; i++)
            {
                StationIndex stationIndex = StationIndex::FromUnderlying(i);
                auto& destStation = dst->getStation(stationIndex);
								
				Json::Value station_j = src["stations"][i];
                if (station_j["station_start"] == "null")
                {
                    destStation.Start.SetNull();
                }
                else
                {
					std::cout<<"e3"<<std::endl;
                    auto tileStartLoc = TileCoordsXY(station_j["station_start_x"].asInt(), station_j["station_start_y"].asInt());
                    destStation.Start = tileStartLoc.ToCoordsXY();
					std::cout<<"e3-2"<<std::endl;
                }
                destStation.Height = station_j["Height"].asUInt();
                destStation.Length = station_j["Length"].asUInt();
                destStation.Depart = station_j["Depart"].asUInt();
                destStation.TrainAtStation = RideStation::kNoTrain; // src->train_at_station[i];
                // Direction is fixed later.

                if (station_j["entrance"] == "null")
                    destStation.Entrance.SetNull();
                else
				{
					std::cout<<"e4"<<std::endl;
					
                    destStation.Entrance = { station_j["entrance_pos"]["x"].asInt(), station_j["entrance_pos"]["y"].asInt(), station_j["entrance_pos"]["z"].asInt(), 0 };
					std::cout<<"e4-2"<<std::endl;
					
				}
                if (station_j["exit"] == "null")
                    destStation.Exit.SetNull();
                else
				{
					std::cout<<"e5"<<std::endl;
                    destStation.Exit = { station_j["exit_pos"]["x"].asInt(), station_j["exit_pos"]["y"].asInt(), station_j["exit_pos"]["z"].asInt(), 0 };
					std::cout<<"e5-2"<<std::endl;
					
				}
                destStation.LastPeepInQueue = EntityId::GetNull(); // EntityId::FromUnderlying(src->last_peep_in_queue[i]);

                destStation.SegmentLength = 0; //src->length[i];
                destStation.SegmentTime = 0; // src->time[i];

                destStation.QueueTime = 0; // src->queue_time[i];

                destStation.QueueLength = 0; // src->queue_length[i];
            }
            // All other values take 0 as their default. Since they're already memset to that, no need to do it again.
            for (int32_t i = Limits::kMaxStationsPerRide; i < OpenRCT2::Limits::kMaxStationsPerRide; i++)
            {
                StationIndex stationIndex = StationIndex::FromUnderlying(i);
                auto& destStation = dst->getStation(stationIndex);

                destStation.Start.SetNull();
                destStation.TrainAtStation = RideStation::kNoTrain;
                destStation.Entrance.SetNull();
                destStation.Exit.SetNull();
                destStation.LastPeepInQueue = EntityId::GetNull();
            }
			
			/*

            for (int32_t i = 0; i < Limits::MaxTrainsPerRide; i++)
            {
                dst->vehicles[i] = EntityId::FromUnderlying(src->vehicles[i]);
            }
            for (int32_t i = Limits::MaxTrainsPerRide - 1; i <= OpenRCT2::Limits::MaxTrainsPerRide; i++)
            {
                dst->vehicles[i] = EntityId::GetNull();
            }

            dst->depart_flags = src->depart_flags;*/

            dst->numStations = 1; //src->numStations;
            //dst->num_vehicles = 1; //src->num_vehicles;
            dst->numCarsPerTrain = 4; // src->numCarsPerTrain;
            /*dst->proposed_num_vehicles = src->proposed_num_vehicles;
            dst->proposed_numCarsPerTrain = src->proposed_numCarsPerTrain;
            dst->max_trains = src->max_trains;
            dst->MinCarsPerTrain = src->GetMinCarsPerTrain();
            dst->MaxCarsPerTrain = src->GetMaxCarsPerTrain();
            dst->min_waiting_time = src->min_waiting_time;
            dst->max_waiting_time = src->max_waiting_time;

            // Includes time_limit, NumLaps, launch_speed, speed, rotations
            dst->operation_option = src->operation_option;

            dst->boat_hire_return_direction = src->boat_hire_return_direction;
            dst->boat_hire_return_position = { src->boat_hire_return_position.x, src->boat_hire_return_position.y };

            dst->special_track_elements = src->special_track_elements;
            // pad_0D6[2];

            dst->max_speed = src->max_speed;
            dst->average_speed = src->average_speed;
            dst->current_test_segment = src->current_test_segment;
            dst->average_speed_test_timeout = src->average_speed_test_timeout;
            // pad_0E2[0x2];

            dst->max_positive_vertical_g = src->max_positive_vertical_g;
            dst->max_negative_vertical_g = src->max_negative_vertical_g;
            dst->max_lateral_g = src->max_lateral_g;
            dst->previous_vertical_g = src->previous_vertical_g;
            dst->previous_lateral_g = src->previous_lateral_g;
            // pad_106[0x2];
            dst->testing_flags = src->testing_flags;

            if (src->cur_test_track_location.IsNull())
            {
                dst->CurTestTrackLocation.SetNull();
            }
            else
            {
                dst->CurTestTrackLocation = { src->cur_test_track_location.x, src->cur_test_track_location.y,
                                              src->cur_test_track_z };
            }

            dst->turn_count_default = src->turn_count_default;
            dst->turn_count_banked = src->turn_count_banked;
            dst->turn_count_sloped = src->turn_count_sloped;
            if (dst->type == RIDE_TYPE_MINI_GOLF)
                dst->holes = src->inversions & 0x1F;
            else
                dst->inversions = src->inversions & 0x1F;
            dst->sheltered_eighths = src->inversions >> 5;
            dst->drops = src->drops;
            dst->start_drop_height = src->start_drop_height;
            dst->highest_drop_height = src->highest_drop_height;
            dst->sheltered_length = src->sheltered_length;
            dst->var_11C = src->var_11C;
            dst->num_sheltered_sections = src->num_sheltered_sections;

            dst->cur_num_customers = src->cur_num_customers;
            dst->num_customers_timeout = src->num_customers_timeout;

            for (uint8_t i = 0; i < Limits::CustomerHistorySize; i++)
            {
                dst->num_customers[i] = src->num_customers[i];
            }*/

            dst->price[0] = 0; //src->price;
			/*
            for (uint8_t i = 0; i < 2; i++)
            {
                dst->ChairliftBullwheelLocation[i] = { src->chairlift_bullwheel_location[i].x,
                                                       src->chairlift_bullwheel_location[i].y, src->chairlift_bullwheel_z[i] };
            }

            dst->ratings = src->ratings;
            dst->value = src->value;

            dst->chairlift_bullwheel_rotation = src->chairlift_bullwheel_rotation;

            dst->satisfaction = src->satisfaction;
            dst->satisfaction_time_out = src->satisfaction_time_out;
            dst->satisfaction_next = src->satisfaction_next;

            dst->window_invalidate_flags = src->window_invalidate_flags;
            // pad_14E[0x02];

            dst->total_customers = src->total_customers;
            dst->total_profit = ToMoney64(src->total_profit);
            dst->popularity = src->popularity;
            dst->popularity_time_out = src->popularity_time_out;
            dst->popularity_next = src->popularity_next;

            ImportNumRiders(dst, rideIndex);

            dst->music_tune_id = src->music_tune_id;
            dst->slide_in_use = src->slide_in_use;
            // Includes maze_tiles
            dst->slide_peep = EntityId::FromUnderlying(src->slide_peep);
            // pad_160[0xE];
            dst->slide_peep_t_shirt_colour = src->slide_peep_t_shirt_colour;
            // pad_16F[0x7];
            dst->spiral_slide_progress = src->spiral_slide_progress;
            // pad_177[0x9];
            dst->build_date = static_cast<int32_t>(src->build_date);
            dst->upkeep_cost = src->upkeep_cost;
            dst->race_winner = EntityId::FromUnderlying(src->race_winner);
            // pad_186[0x02];
            dst->music_position = src->music_position;

            dst->breakdown_reason_pending = src->breakdown_reason_pending;
            dst->mechanic_status = src->mechanic_status;
            dst->mechanic = EntityId::FromUnderlying(src->mechanic);
            dst->inspection_station = StationIndex::FromUnderlying(src->inspection_station);
            dst->broken_vehicle = src->broken_vehicle;
            dst->broken_car = src->broken_car;
            dst->breakdown_reason = src->breakdown_reason;

            dst->price[1] = src->price_secondary;

            dst->reliability = src->reliability;
            dst->unreliability_factor = src->unreliability_factor;
            dst->downtime = src->downtime;
            dst->inspection_interval = src->inspection_interval;
            dst->last_inspection = src->last_inspection;

            for (uint8_t i = 0; i < Limits::DowntimeHistorySize; i++)
            {
                dst->downtime_history[i] = src->downtime_history[i];
            }

            dst->no_primary_items_sold = src->no_primary_items_sold;
            dst->no_secondary_items_sold = src->no_secondary_items_sold;

            dst->breakdown_sound_modifier = src->breakdown_sound_modifier;
            dst->not_fixed_timeout = src->not_fixed_timeout;
            dst->last_crash_type = src->last_crash_type;
            dst->connected_message_throttle = src->connected_message_throttle;

            dst->income_per_hour = ToMoney64(src->income_per_hour);
            dst->profit = ToMoney64(src->profit);

            for (uint8_t i = 0; i < Limits::NumColourSchemes; i++)
            {
                dst->track_colour[i].main = src->track_colour_main[i];
                dst->track_colour[i].additional = src->track_colour_additional[i];
                dst->track_colour[i].supports = src->track_colour_supports[i];
            }
            // This stall was not colourable in RCT2.
            if (dst->type == RIDE_TYPE_FOOD_STALL)
            {
                auto object = object_entry_get_object(ObjectType::Ride, dst->subtype);
                if (object != nullptr && object->GetIdentifier() == "rct2.ride.icecr1")
                {
                    dst->track_colour[0].main = COLOUR_LIGHT_BLUE;
                }
            }

            auto musicStyle = kObjectEntryIndexNull;
            if (GetRideTypeDescriptor(dst->type).HasFlag(RIDE_TYPE_FLAG_ALLOW_MUSIC))
            {
                musicStyle = src->music;
            }
            dst->music = musicStyle;

            // In SV7, "plain" entrances are invisible.
            auto entranceStyle = kObjectEntryIndexNull;
            if (!_isSV7 && GetRideTypeDescriptor(dst->type).HasFlag(RIDE_TYPE_FLAG_HAS_ENTRANCE_EXIT))
            {
                entranceStyle = src->entrance_style;
            }
            dst->entrance_style = entranceStyle;

            dst->vehicle_change_timeout = src->vehicle_change_timeout;
            dst->num_block_brakes = src->num_block_brakes;
            dst->lift_hill_speed = src->lift_hill_speed;
            dst->guests_favourite = src->guests_favourite;
            dst->lifecycle_flags = src->lifecycle_flags;

            for (uint8_t i = 0; i < Limits::MaxTrainsPerRide; i++)
            {
                dst->vehicle_colours[i].Tertiary = src->vehicle_colours_extended[i];
            }

            dst->total_air_time = src->total_air_time;
            dst->current_test_station = StationIndex::FromUnderlying(src->current_test_station);
            dst->num_circuits = src->num_circuits;
            dst->CableLiftLoc = { src->cable_lift_x, src->cable_lift_y, src->cable_lift_z * COORDS_Z_STEP };
            // pad_1FD;
            dst->cable_lift = EntityId::FromUnderlying(src->cable_lift);

            // pad_208[0x58];
			*/
        }
		
        void ImportRideRatingsCalcData()
        {
            const auto& src = _s6.RideRatingsCalcData;
            // S6 has only one state, ensure we reset all states before reading the first one.
            RideRatingResetUpdateStates();
            auto& rideRatingStates = getGameState().rideRatingUpdateStates;
            auto& dst = rideRatingStates[0];
            dst = {};
            dst.Proximity = { src.ProximityX, src.ProximityY, src.ProximityZ };
            dst.ProximityStart = { src.ProximityStartX, src.ProximityStartY, src.ProximityStartZ };
            dst.CurrentRide = RCT12RideIdToOpenRCT2RideId(src.CurrentRide);
            dst.State = src.State;
            if (src.CurrentRide < Limits::kMaxRidesInPark && _s6.Rides[src.CurrentRide].type < std::size(kRideTypeDescriptors))
            {
                dst.ProximityTrackType = RCT2TrackTypeToOpenRCT2(
                    src.ProximityTrackType, _s6.Rides[src.CurrentRide].type, IsFlatRide(src.CurrentRide));
            }
            else
            {
                dst.ProximityTrackType = TrackElemType::None;
            }
            dst.ProximityBaseHeight = src.ProximityBaseHeight;
            dst.ProximityTotal = src.ProximityTotal;
            for (size_t i = 0; i < std::size(src.ProximityScores); i++)
            {
                dst.ProximityScores[i] = src.ProximityScores[i];
            }
            dst.AmountOfBrakes = src.NumBrakes;
            dst.AmountOfReversers = src.NumReversers;
            dst.StationFlags = src.StationFlags;
        }
		
        void ImportRideMeasurements()
        {
            for (const auto& src : _s6.RideMeasurements)
            {
                if (src.RideIndex != kRCT12RideIdNull)
                {
                    const auto rideId = RideId::FromUnderlying(src.RideIndex);
                    auto ride = GetRide(rideId);
                    if (ride != nullptr)
                    {
                        ride->measurement = std::make_unique<RideMeasurement>();
                        ImportRideMeasurement(*ride->measurement, src);
                    }
                }
            }
        }


        void ImportRideMeasurement(RideMeasurement& dst, const RCT12RideMeasurement& src)
        {
            dst.flags = src.Flags;
            dst.last_use_tick = src.LastUseTick;
            dst.num_items = src.NumItems;
            dst.current_item = src.CurrentItem;
            dst.vehicle_index = src.VehicleIndex;
            dst.current_station = StationIndex::FromUnderlying(src.CurrentStation);
            for (size_t i = 0; i < std::size(src.Velocity); i++)
            {
                dst.velocity[i] = src.Velocity[i];
                dst.altitude[i] = src.Altitude[i];
                dst.vertical[i] = src.Vertical[i];
                dst.lateral[i] = src.Lateral[i];
            }
        }

        void ImportResearchList(GameState_t& gameState)
        {
            bool invented = true;
            for (const auto& researchItem : _s6.ResearchItems)
            {
                if (researchItem.IsInventedEndMarker())
                {
                    invented = false;
                    continue;
                }
                if (researchItem.IsUninventedEndMarker() || researchItem.IsRandomEndMarker())
                {
                    break;
                }

                if (invented)
                    gameState.researchItemsInvented.emplace_back(researchItem.ToResearchItem());
                else
                    gameState.researchItemsUninvented.emplace_back(researchItem.ToResearchItem());
            }
        }

        void ImportBanner(Banner* dst, const RCT12Banner* src)
        {
            auto id = dst->id;

            *dst = {};
            dst->id = id;
            dst->type = RCTEntryIndexToOpenRCT2EntryIndex(src->Type);
            dst->flags = src->Flags;

            if (!(src->Flags & BANNER_FLAG_LINKED_TO_RIDE) && IsUserStringID(src->StringID))
            {
                dst->text = GetUserString(src->StringID);
            }

            if (src->Flags & BANNER_FLAG_LINKED_TO_RIDE)
            {
                dst->ride_index = RCT12RideIdToOpenRCT2RideId(src->RideIndex);
            }
            else
            {
                dst->colour = src->Colour;
            }

            dst->text_colour = src->TextColour;
            dst->position.x = src->x;
            dst->position.y = src->y;
        }

        void Initialise()
        {
			std::cout<<"e6"<<std::endl;
			
			gameStateInitAll(getGameState(), { _json["map_size"]["x"].asInt(), _json["map_size"]["y"].asInt() });
			std::cout<<"e6-2"<<std::endl;
			
        }

        /**
         * Imports guest entry points.
         * Includes fixes for incorrectly set guest entry points in some scenarios.
         */
        void ImportpeepSpawns()
        {
            // Many WW and TT have scenario_filename fields containing an incorrect filename. Check for both this filename
            // and the corrected filename.
			
			/*
            // In this park, peep_spawns[0] is incorrect, and peep_spawns[1] is correct.
            if (String::equals(_s6.scenario_filename, "WW South America - Rio Carnival.SC6")
                || String::equals(_s6.scenario_filename, "South America - Rio Carnival.SC6"))
            {
                _s6.peep_spawns[0] = { 2160, 3167, 6, 1 };
                _s6.peep_spawns[1].x = RCT12_PEEP_SPAWN_UNDEFINED;
            }
            // In this park, peep_spawns[0] is correct. Just clear the other.
            else if (
                String::equals(_s6.scenario_filename, "Great Wall of China Tourism Enhancement.SC6")
                || String::equals(_s6.scenario_filename, "Asia - Great Wall of China Tourism Enhancement.SC6"))
            {
                _s6.peep_spawns[1].x = RCT12_PEEP_SPAWN_UNDEFINED;
            }
            // Amity Airfield has peeps entering from the corner of the tile, instead of the middle.
            else if (String::equals(_s6.scenario_filename, "Amity Airfield.SC6"))
            {
                _s6.peep_spawns[0].y = 1296;
            }
            // #9926: Africa - Oasis has peeps spawning on the edge underground near the entrance
            else if (String::equals(_s6.scenario_filename, "Africa - Oasis.SC6"))
            {
                _s6.peep_spawns[0].y = 2128;
                _s6.peep_spawns[0].z = 7;
            }*/

            getGameState().peepSpawns.clear();
			std::cout<<"e7"<<std::endl;
			
			for (unsigned int i = 0; i < _json["spawns"].size(); i ++)
			{
				Json::Value spawn_j = _json["spawns"][i];
                PeepSpawn spawn = { spawn_j["x"].asInt(), spawn_j["y"].asInt(), spawn_j["z"].asInt(), static_cast<Direction>(spawn_j["direction"].asUInt()) };
                getGameState().peepSpawns.push_back(spawn);
			}
			std::cout<<"e7-2"<<std::endl;
			
			/*
            for (size_t i = 0; i < Limits::MaxpeepSpawns; i++)
            {
                if (_s6.peep_spawns[i].x != RCT12_PEEP_SPAWN_UNDEFINED)
                {
                    PeepSpawn spawn = { _s6.peep_spawns[i].x, _s6.peep_spawns[i].y, _s6.peep_spawns[i].z * 16,
                                        _s6.peep_spawns[i].direction };
                    gpeepSpawns.push_back(spawn);
                }
            }*/
        }

        void ImportNumRiders(::Ride* dst, const RideId rideIndex)
        {
            // The number of riders might have overflown or underflown. Re-calculate the value.
            uint16_t numRiders = 0;
            for (int32_t i = 0; i < Limits::kMaxEntities; i++)
            {
                const auto& entity = _s6.Entities[i];
                if (entity.Unknown.EntityIdentifier == RCT12EntityIdentifier::Peep)
                {
                    if (entity.Peep.CurrentRide == static_cast<RCT12RideId>(rideIndex.ToUnderlying())
                        && (static_cast<PeepState>(entity.Peep.State) == PeepState::OnRide
                            || static_cast<PeepState>(entity.Peep.State) == PeepState::EnteringRide))
                    {
                        numRiders++;
                    }
                }
            }
            dst->numRiders = numRiders;
        }
		
        void ImportTileElements()
        {
            // Build tile pointer cache (needed to get the first element at a certain location)
            //auto tilePointerIndex = TilePointerIndex<RCT12TileElement>(
            //    Limits::MaxMapSize, _s6.tile_elements, std::size(_s6.tile_elements));

            std::vector<TileElement> tileElements;
            //bool nextElementInvisible = false;
            //bool restOfTileInvisible = false;
            //const auto maxSize = std::min(Limits::MaxMapSize, _s6.map_size);
			
			std::cout<<"start tiles\n";
            for (TileCoordsXY coords = { 0, 0 }; coords.y < kMaximumMapSizeTechnical; coords.y++)
            {
                for (coords.x = 0; coords.x < kMaximumMapSizeTechnical; coords.x++)
                {
                    auto tileAdded = false;
					auto x = std::to_string(coords.x);
					auto y = std::to_string(coords.y);
					for (unsigned int i = 0; i < _json["map"][x][y].size(); i ++)
					{
						//std::cout<<i<<",\n";
						auto srcElement = _json["map"][x][y][i];
                        auto& dstElement = tileElements.emplace_back();
                        ImportTileElement(&dstElement, srcElement); //, false); //nextElementInvisible || restOfTileInvisible);
                        tileAdded = true;
					}
					
                    if (!tileAdded)
                    {
                        // Add a default surface element, we always need at least one element per tile
                        auto& dstElement = tileElements.emplace_back();
                        dstElement.ClearAs(TileElementType::Surface);
                        dstElement.SetLastForTile(true);
                    }

                    // Set last element flag in case the original last element was never added
                    if (tileElements.size() > 0)
                    {
                        tileElements.back().SetLastForTile(true);
                    }
					/*
                    nextElementInvisible = false;
                    restOfTileInvisible = false;

                    auto tileAdded = false;
                    if (coords.x < maxSize && coords.y < maxSize)
                    {
                        const auto* srcElement = tilePointerIndex.GetFirstElementAt(coords);
                        if (srcElement != nullptr)
                        {
                            do
                            {
                                if (srcElement->base_height == RCT12::Limits::MaxElementHeight)
                                {
                                    continue;
                                }

                                auto tileElementType = srcElement->GetType();
                                if (tileElementType == RCT12TileElementType::Corrupt)
                                {
                                    // One property of corrupt elements was to hide tops of tower tracks, and to avoid the next
                                    // element from being hidden, multiple consecutive corrupt elements were sometimes used.
                                    // This would essentially toggle the flag, so we inverse nextElementInvisible here instead
                                    // of always setting it to true.
                                    nextElementInvisible = !nextElementInvisible;
                                    continue;
                                }
                                if (tileElementType == RCT12TileElementType::EightCarsCorrupt14
                                    || tileElementType == RCT12TileElementType::EightCarsCorrupt15)
                                {
                                    restOfTileInvisible = true;
                                    continue;
                                }

                                auto& dstElement = tileElements.emplace_back();
                                ImportTileElement(&dstElement, srcElement, nextElementInvisible || restOfTileInvisible);
                                nextElementInvisible = false;
                                tileAdded = true;
                            } while (!(srcElement++)->IsLastForTile());
                        }
                    }

                    if (!tileAdded)
                    {
                        // Add a default surface element, we always need at least one element per tile
                        auto& dstElement = tileElements.emplace_back();
                        dstElement.ClearAs(TileElementType::Surface);
                        dstElement.SetLastForTile(true);
                    }

                    // Set last element flag in case the original last element was never added
                    if (tileElements.size() > 0)
                    {
                        tileElements.back().SetLastForTile(true);
                    }*/
                }
            }
            SetTileElements(getGameState(), std::move(tileElements));
        }

        void ImportTileElement(TileElement* dst, Json::Value src) //const RCT12TileElement* src, bool invisible)
        {
            const auto elementType = static_cast<TileElementType>(src["type"].asUInt());
            dst->ClearAs(elementType); //ToOpenRCT2TileElementType(rct12Type));
            dst->SetDirection(src["direction"].asUInt());
            dst->SetBaseZ(src["base_z"].asInt()); // * COORDS_Z_STEP);
            dst->SetClearanceZ(src["clearance_z"].asInt()); // * COORDS_Z_STEP);

            // All saved in "flags"
            dst->SetOccupiedQuadrants(src["quadrants"].asUInt()); //src->GetOccupiedQuadrants());
            //dst->SetGhost(src->IsGhost());
            dst->SetLastForTile(false); //src->IsLastForTile());
            //dst->SetInvisible(invisible);

            switch (elementType)
            {
			    case TileElementType::Surface:
				{
                    auto dst2 = dst->AsSurface();

                    dst2->SetSlope(src["slope"].asUInt());
										
					auto identifier = src["surface_obj_id"].asString();
					auto desc = ObjectEntryDescriptor(identifier);
					auto textureID = ObjectManagerGetLoadedObjectEntryIndex(desc);
                    dst2->SetSurfaceObjectIndex(textureID);
					
					auto identifier2 = src["edge_obj_id"].asString();
					auto desc2 = ObjectEntryDescriptor(identifier2);
					auto textureID2 = ObjectManagerGetLoadedObjectEntryIndex(desc2);
                    dst2->SetEdgeObjectIndex(textureID2);
					
				    /*auto& objectMgr = OpenRCT2::GetContext()->GetObjectManager();
		            dst->subtype = objectMgr.GetLoadedObjectEntryIndex(identifier); //subtype;
					if (dst->subtype == kObjectEntryIndexNull)
					{
						std::cout << "could not find this subtype <"<<identifier<<">\n";
					}*/
					

                    dst2->SetGrassLength(GRASS_LENGTH_CLEAR_0); //src2->GetGrassLength());
                    dst2->SetOwnership(OWNERSHIP_OWNED); //src2->GetOwnership());
                    dst2->SetParkFences(0); //src2->GetParkFences());
                    dst2->SetWaterHeight(src["water_height"].asUInt());
                    dst2->SetHasTrackThatNeedsWater(false); //src2->HasTrackThatNeedsWater());
					
					break;
				}
			    case TileElementType::Path:
				{
                    auto dst2 = dst->AsPath();
					
                    if (src["legacy"].asBool())
                    {
                        // Legacy footpath object
	                    //auto pathEntryIndex = src["entry_index"].asUInt(); //->GetEntryIndex();
                        //dst2->SetLegacyPathEntryIndex(pathEntryIndex);
						
					    /*auto& objectMgr = OpenRCT2::GetContext()->GetObjectManager();
			            auto pathEntryIndex = objectMgr.GetLoadedObjectEntryIndex(identifier); //subtype;
                        dst2->SetLegacyPathEntryIndex(pathEntryIndex);
						*/
						// TODO
						std::cout<<"alert-legacy path not implemented\n";
                    }
                    else
                    {
	                    //auto surfaceEntry = src["queue"].asBool() ? _pathToQueueSurfaceMap[pathEntryIndex]
	                    //                                    : _pathToSurfaceMap[pathEntryIndex];
						
                        // Surface / railing
                        //dst2->SetSurfaceEntryIndex(src["surface_entry_index"].asUInt());
                        //dst2->SetRailingsEntryIndex(src["railing_entry_index"].asUInt());
						

										
						auto identifier = src["surface_obj_id"].asString();
						auto textureID = ObjectManagerGetLoadedObjectEntryIndex(ObjectEntryDescriptor(identifier));
	                    dst2->SetSurfaceEntryIndex(textureID);
					
						auto identifier2 = src["railing_obj_id"].asString();
						auto textureID2 = ObjectManagerGetLoadedObjectEntryIndex(ObjectEntryDescriptor(identifier2));
	                    dst2->SetRailingsEntryIndex(textureID2);
                    }

                    dst2->SetQueueBannerDirection(0); //src2->GetQueueBannerDirection());
                    dst2->SetSloped(src["sloped"].asBool()); //src2->IsSloped());
                    dst2->SetSlopeDirection(src["slope_direction"].asUInt()); //src2->GetSlopeDirection());
                    dst2->SetIsQueue(src["queue"].asBool());
                    dst2->SetRideIndex(RideId::FromUnderlying(src["ride_index"].asUInt())); //RCT12RideIdToOpenRCT2RideId(src2->GetRideIndex()));
                    dst2->SetStationIndex(StationIndex::FromUnderlying(src["station_index"].asUInt())); //src2->getStationIndex()));
                    dst2->SetWide(false); //src2->IsWide());
                    dst2->SetHasQueueBanner(false); //src2->HasQueueBanner());
                    dst2->SetEdges(src["edges"].asUInt());
                    dst2->SetCorners(0); //src2->GetCorners());
                    dst2->SetAddition(0); //src2->GetAddition());
                    dst2->SetAdditionIsGhost(false); //src2->AdditionIsGhost());
                    dst2->SetAdditionStatus(255); //src2->GetAdditionStatus());
                    dst2->SetIsBroken(false); //src2->IsBroken());
                    dst2->SetIsBlockedByVehicle(false); //src2->IsBlockedByVehicle());
					
					break;
				}
			    case TileElementType::Track:
				{
                    auto dst2 = dst->AsTrack();
					
                    auto rideType = src["ride_type"].asUInt(); // _s6.rides[src2->GetRideIndex()].type;
                    TrackElemType trackType = static_cast<TrackElemType>(src["track_type"].asUInt());

                    dst2->SetTrackType(trackType); //RCT2TrackTypeToOpenRCT2(trackType, rideType, IsFlatRide(src2->GetRideIndex())));
                    dst2->SetRideType(rideType);
                    dst2->SetSequenceIndex(src["sequence_index"].asUInt());
                    dst2->SetRideIndex(RideId::FromUnderlying(src["ride_index"].asUInt())); //RCT12RideIdToOpenRCT2RideId(src2->GetRideIndex()));
                    dst2->SetColourScheme(RideColourScheme::main); //src2->GetColourScheme());
                    dst2->SetHasChain(src["has_chain"].asBool());
                    dst2->SetHasCableLift(src["has_cable_lift"].asBool()); //src2->HasCableLift());
                    dst2->SetInverted(src["is_inverted"].asBool()); //src2->IsInverted());
                    dst2->SetStationIndex(StationIndex::FromUnderlying(src["station_index"].asUInt())); //src2->getStationIndex()));
					
                    dst2->SetHasGreenLight(false); //src2->HasGreenLight());
                    dst2->SetBrakeClosed(false); //src2->BlockBrakeClosed());
                    dst2->SetIsIndestructible(false); //src2->IsIndestructible());
                    // Skipping IsHighlighted()

                    if (TrackTypeHasSpeedSetting(trackType))
                    {
                        //dst2->SetBrakeBoosterSpeed(src2->GetBrakeBoosterSpeed());
                    }
                    else if (trackType == TrackElemType::OnRidePhoto)
                    {
                        dst2->SetPhotoTimeout(); //src2->GetPhotoTimeout());
                    }

                    // This has to be done last, since the maze entry shares fields with the colour and sequence fields.
                    if (rideType == RIDE_TYPE_MAZE)
                    {
                        dst2->SetMazeEntry(0xFFFF); //src2->GetMazeEntry());
                    }
                    else if (rideType == RIDE_TYPE_GHOST_TRAIN)
                    {
                        dst2->SetDoorAState(LANDSCAPE_DOOR_CLOSED); //src2->GetDoorAState());
                        dst2->SetDoorBState(LANDSCAPE_DOOR_CLOSED); //src2->GetDoorBState());
                    }
                    else
                    {
                        dst2->SetSeatRotation(DEFAULT_SEAT_ROTATION); //src2->GetSeatRotation());
                    }
					
					break;
				}
			    case TileElementType::SmallScenery:
				{
                    auto dst2 = dst->AsSmallScenery();

					auto identifier = src["obj_id"].asString();
				    auto& objectMgr = OpenRCT2::GetContext()->GetObjectManager();
		            auto entryIndex = objectMgr.GetLoadedObjectEntryIndex(identifier); //subtype;
					if (entryIndex == kObjectEntryIndexNull)
					{
						std::cout << "could not find small scenery ID <"<<identifier<<">\n";
					}
                    dst2->SetEntryIndex(entryIndex);
					
                    dst2->SetAge(0); //src2->GetAge());
                    dst2->SetSceneryQuadrant(src["scenery_quadrant"].asUInt());
                    dst2->SetPrimaryColour(src["primary_colour"].asUInt());
                    dst2->SetSecondaryColour(src["secondary_colour"].asUInt());
                    //if (src2->NeedsSupports())
                    //    dst2->SetNeedsSupports();
										
					break;
				}
			    case TileElementType::Entrance:
				{
                    auto dst2 = dst->AsEntrance();

                    dst2->SetEntranceType(src["entranceType"].asUInt());
                    dst2->SetRideIndex(RideId::FromUnderlying(src["ride_index"].asUInt())); //RCT12RideIdToOpenRCT2RideId(src2->GetRideIndex()));
                    dst2->SetStationIndex(StationIndex::FromUnderlying(src["station_index"].asUInt())); //src2->getStationIndex()));
                    dst2->SetSequenceIndex(src["sequence_index"].asUInt());

                    /*if (src["sequence_index"].asUInt() == 0)
                    {
                        auto pathEntryIndex = src2->GetPathType();
                        auto surfaceEntry = _pathToSurfaceMap[pathEntryIndex];
                        if (surfaceEntry == kObjectEntryIndexNull)
                        {
                            // Legacy footpath object
                            dst2->SetLegacyPathEntryIndex(pathEntryIndex);
                        }
                        else
                        {
                            // Surface
                            dst2->SetSurfaceEntryIndex(surfaceEntry);
                        }
                    }
                    else*/
                    {
                        dst2->SetSurfaceEntryIndex(kObjectEntryIndexNull);
                    }
                    break;
				}
			    case TileElementType::Wall:
				{
                    auto dst2 = dst->AsWall();

					auto identifier = src["obj_id"].asString();
				    auto& objectMgr = OpenRCT2::GetContext()->GetObjectManager();
		            auto entryIndex = objectMgr.GetLoadedObjectEntryIndex(identifier); //subtype;
					if (entryIndex == kObjectEntryIndexNull)
					{
						std::cout << "could not find wall ID <"<<identifier<<">\n";
					}
                    dst2->SetEntryIndex(entryIndex);

                    dst2->SetSlope(src["slope"].asUInt());
                    dst2->SetPrimaryColour(src["primary_colour"].asUInt());
                    dst2->SetSecondaryColour(src["secondary_colour"].asUInt());
                    dst2->SetTertiaryColour(src["tertiary_colour"].asUInt());
					
					
                    //dst2->SetAnimationFrame(src2->GetAnimationFrame());
                    dst2->SetAcrossTrack(false); //src2->IsAcrossTrack());
                    dst2->SetAnimationIsBackwards(false); //src2->AnimationIsBackwards());

                    // Import banner information
                    dst2->SetBannerIndex(BannerIndex::GetNull());
                    auto entry = dst2->GetEntry();
                    /*if (entry != nullptr && entry->scrolling_mode != SCROLLING_MODE_NONE)
                    {
                        auto bannerIndex = src2->GetBannerIndex();
                        if (bannerIndex < std::size(_s6.banners))
                        {
                            auto srcBanner = &_s6.banners[bannerIndex];
                            auto dstBanner = GetOrCreateBanner(BannerIndex::FromUnderlying(bannerIndex));
                            if (dstBanner == nullptr)
                            {
                                dst2->SetBannerIndex(BannerIndex::GetNull());
                            }
                            else
                            {
                                ImportBanner(dstBanner, srcBanner);
                                dst2->SetBannerIndex(BannerIndex::FromUnderlying(src2->GetBannerIndex()));
                            }
                        }
                    }*/
                    break;
				}
			    case TileElementType::LargeScenery:
				{
                    auto dst2 = dst->AsLargeScenery();

					auto identifier = src["obj_id"].asString();
				    auto& objectMgr = OpenRCT2::GetContext()->GetObjectManager();
		            auto entryIndex = objectMgr.GetLoadedObjectEntryIndex(identifier); //subtype;
					if (entryIndex == kObjectEntryIndexNull)
					{
						std::cout << "could not find large scenery ID <"<<identifier<<">\n";
					}
                    dst2->SetEntryIndex(entryIndex);

                    dst2->SetSequenceIndex(src["sequence_index"].asUInt());
                    dst2->SetPrimaryColour(src["primary_colour"].asUInt());
                    dst2->SetSecondaryColour(src["secondary_colour"].asUInt());

                    // Import banner information
					/*
                    dst2->SetBannerIndex(BannerIndex::GetNull());
                    auto entry = dst2->GetEntry();
                    if (entry != nullptr && entry->scrolling_mode != SCROLLING_MODE_NONE)
                    {
                        auto bannerIndex = src2->GetBannerIndex();
                        if (bannerIndex < std::size(_s6.banners))
                        {
                            auto srcBanner = &_s6.banners[bannerIndex];
                            auto dstBanner = GetOrCreateBanner(BannerIndex::FromUnderlying(bannerIndex));
                            if (dstBanner == nullptr)
                            {
                                dst2->SetBannerIndex(BannerIndex::GetNull());
                            }
                            else
                            {
                                ImportBanner(dstBanner, srcBanner);
                                dst2->SetBannerIndex(BannerIndex::FromUnderlying(src2->GetBannerIndex()));
                            }
                        }
                    }*/
					break;
				}
			    case TileElementType::Banner:
				{
					// ignore for now.
					break;
					
					/*
                    auto dst2 = dst->AsBanner();
                    auto src2 = src->AsBanner();

                    dst2->SetPosition(src2->GetPosition());
                    dst2->SetAllowedEdges(src2->GetAllowedEdges());

                    auto bannerIndex = src2->GetIndex();
                    if (bannerIndex < std::size(_s6.banners))
                    {
                        auto srcBanner = &_s6.banners[bannerIndex];
                        auto dstBanner = GetOrCreateBanner(BannerIndex::FromUnderlying(bannerIndex));
                        if (dstBanner == nullptr)
                        {
                            dst2->SetIndex(BannerIndex::GetNull());
                        }
                        else
                        {
                            ImportBanner(dstBanner, srcBanner);
                            dst2->SetIndex(BannerIndex::FromUnderlying(bannerIndex));
                        }
                    }
                    else
                    {
                        dst2->SetIndex(BannerIndex::GetNull());
                    }
                    break;
					*/
				}
				
                default:
                    assert(false);
            }
        }

        void ImportmarketingCampaigns()
        {
            for (size_t i = 0; i < ADVERTISING_CAMPAIGN_COUNT; i++)
            {
                if (_s6.CampaignWeeksLeft[i] & CAMPAIGN_ACTIVE_FLAG)
                {
                    MarketingCampaign campaign{};
                    campaign.Type = static_cast<uint8_t>(i);
                    campaign.WeeksLeft = _s6.CampaignWeeksLeft[i] & ~(CAMPAIGN_ACTIVE_FLAG | CAMPAIGN_FIRST_WEEK_FLAG);
                    if ((_s6.CampaignWeeksLeft[i] & CAMPAIGN_FIRST_WEEK_FLAG) != 0)
                    {
                        campaign.Flags |= MarketingCampaignFlags::FIRST_WEEK;
                    }
                    if (campaign.Type == ADVERTISING_CAMPAIGN_RIDE_FREE || campaign.Type == ADVERTISING_CAMPAIGN_RIDE)
                    {
                        campaign.RideId = RCT12RideIdToOpenRCT2RideId(_s6.CampaignRideIndex[i]);
                    }
                    else if (campaign.Type == ADVERTISING_CAMPAIGN_FOOD_OR_DRINK_FREE)
                    {
                        campaign.ShopItemType = ShopItem(_s6.CampaignRideIndex[i]);
                    }
                    getGameState().marketingCampaigns.push_back(campaign);
                }
            }
        }

        void ImportStaffPatrolArea(Staff* staffmember, uint8_t staffId)
        {
            // First check staff mode as vanilla did not clean up patrol areas when switching from patrol to walk
            // without doing this we could accidentally add a patrol when it didn't exist.
            if (_s6.StaffModes[staffId] != StaffMode::Patrol)
            {
                return;
            }
            int32_t peepOffset = staffId * Limits::kPatrolAreaSize;
            for (int32_t i = 0; i < Limits::kPatrolAreaSize; i++)
            {
                if (_s6.PatrolAreas[peepOffset + i] == 0)
                {
                    // No patrol for this area
                    continue;
                }

                // Loop over the bits of the uint32_t
                for (int32_t j = 0; j < 32; j++)
                {
                    int8_t bit = (_s6.PatrolAreas[peepOffset + i] >> j) & 1;
                    if (bit == 0)
                    {
                        // No patrol for this area
                        continue;
                    }
                    // val contains the 6 highest bits of both the x and y coordinates
                    int32_t val = j | (i << 5);
                    int32_t x = val & 0x03F;
                    x <<= 7;
                    int32_t y = val & 0xFC0;
                    y <<= 1;
                    staffmember->SetPatrolArea(MapRange(x, y, x + (4 * kCoordsXYStep) - 1, y + (4 * kCoordsXYStep) - 1), true);
                }
            }
        }

        
        void ImportEntities()
        {
            for (int32_t i = 0; i < Limits::kMaxEntities; i++)
            {
                ImportEntity(_s6.Entities[i].Unknown);
            }
        }

        template<typename OpenRCT2_T> void ImportEntity(const RCT12EntityBase& src);

        void ImportEntityPeep(::Peep* dst, const Peep* src)
        {
            const auto isNullLocation = [](const RCT12xyzd8& pos) {
                return pos.x == 0xFF && pos.y == 0xFF && pos.z == 0xFF && pos.direction == kInvalidDirection;
            };

            ImportEntityCommonProperties(static_cast<EntityBase*>(dst), src);
            if (IsUserStringID(src->NameStringIdx))
            {
                dst->SetName(GetUserString(src->NameStringIdx));
            }
            dst->NextLoc = { src->NextX, src->NextY, src->NextZ * kCoordsZStep };
            dst->NextFlags = src->NextFlags;
            dst->State = static_cast<PeepState>(src->State);
            dst->SubState = src->SubState;

            // TODO
            dst->AnimationObjectIndex = kObjectEntryIndexNull;
            dst->AnimationGroup = static_cast<PeepAnimationGroup>(src->AnimationGroup);

            dst->TshirtColour = src->TshirtColour;
            dst->TrousersColour = src->TrousersColour;
            dst->DestinationX = src->DestinationX;
            dst->DestinationY = src->DestinationY;
            dst->DestinationTolerance = src->DestinationTolerance;
            dst->Var37 = src->Var37;
            dst->Energy = src->Energy;
            dst->EnergyTarget = src->EnergyTarget;
            dst->Mass = src->Mass;
            dst->WindowInvalidateFlags = src->WindowInvalidateFlags;
            dst->CurrentRide = RCT12RideIdToOpenRCT2RideId(src->CurrentRide);
            dst->CurrentRideStation = StationIndex::FromUnderlying(src->CurrentRideStation);
            dst->CurrentTrain = src->CurrentTrain;
            dst->TimeToSitdown = src->TimeToSitdown;
            dst->SpecialSprite = src->SpecialSprite;
            dst->AnimationType = static_cast<PeepAnimationType>(src->AnimationType);
            dst->NextAnimationType = static_cast<PeepAnimationType>(src->NextAnimationType);
            dst->AnimationImageIdOffset = src->AnimationImageIdOffset;
            dst->Action = static_cast<PeepActionType>(src->Action);
            dst->AnimationFrameNum = src->AnimationFrameNum;
            dst->StepProgress = src->StepProgress;
            dst->PeepDirection = src->Direction;
            dst->InteractionRideIndex = RCT12RideIdToOpenRCT2RideId(src->InteractionRideIndex);
            dst->PeepId = src->Id;
            dst->PathCheckOptimisation = src->PathCheckOptimisation;
            dst->PeepFlags = src->PeepFlags;
            if (isNullLocation(src->PathfindGoal))
            {
                dst->PathfindGoal.SetNull();
                dst->PathfindGoal.direction = kInvalidDirection;
            }
            else
            {
                dst->PathfindGoal = { src->PathfindGoal.x, src->PathfindGoal.y, src->PathfindGoal.z,
                                      src->PathfindGoal.direction };
            }
            for (size_t i = 0; i < std::size(src->PathfindHistory); i++)
            {
                if (isNullLocation(src->PathfindHistory[i]))
                {
                    dst->PathfindHistory[i].SetNull();
                    dst->PathfindHistory[i].direction = kInvalidDirection;
                }
                else
                {
                    dst->PathfindHistory[i] = { src->PathfindHistory[i].x, src->PathfindHistory[i].y, src->PathfindHistory[i].z,
                                                src->PathfindHistory[i].direction };
                }
            }
            dst->WalkingAnimationFrameNum = src->NoActionFrameNum;
        }

        constexpr EntityType GetEntityTypeFromRCT2Sprite(const RCT12EntityBase* src)
        {
            EntityType output = EntityType::Null;
            switch (src->EntityIdentifier)
            {
                case RCT12EntityIdentifier::Vehicle:
                    output = EntityType::Vehicle;
                    break;
                case RCT12EntityIdentifier::Peep:
                {
                    const auto& peep = static_cast<const Peep&>(*src);
                    if (RCT12PeepType(peep.PeepType) == RCT12PeepType::Guest)
                    {
                        output = EntityType::Guest;
                    }
                    else
                    {
                        output = EntityType::Staff;
                    }
                    break;
                }
                case RCT12EntityIdentifier::Misc:

                    switch (RCT12MiscEntityType(src->Type))
                    {
                        case RCT12MiscEntityType::SteamParticle:
                            output = EntityType::SteamParticle;
                            break;
                        case RCT12MiscEntityType::MoneyEffect:
                            output = EntityType::MoneyEffect;
                            break;
                        case RCT12MiscEntityType::CrashedVehicleParticle:
                            output = EntityType::CrashedVehicleParticle;
                            break;
                        case RCT12MiscEntityType::ExplosionCloud:
                            output = EntityType::ExplosionCloud;
                            break;
                        case RCT12MiscEntityType::CrashSplash:
                            output = EntityType::CrashSplash;
                            break;
                        case RCT12MiscEntityType::ExplosionFlare:
                            output = EntityType::ExplosionFlare;
                            break;
                        case RCT12MiscEntityType::JumpingFountainWater:
                        case RCT12MiscEntityType::JumpingFountainSnow:
                            output = EntityType::JumpingFountain;
                            break;
                        case RCT12MiscEntityType::Balloon:
                            output = EntityType::Balloon;
                            break;
                        case RCT12MiscEntityType::Duck:
                            output = EntityType::Duck;
                            break;
                        default:
                            break;
                    }
                    break;
                case RCT12EntityIdentifier::Litter:
                    output = EntityType::Litter;
                    break;
                default:
                    break;
            }
            return output;
        }

        void ImportEntityCommonProperties(EntityBase* dst, const RCT12EntityBase* src)
        {
            dst->Type = GetEntityTypeFromRCT2Sprite(src);
            dst->SpriteData.HeightMin = src->SpriteHeightNegative;
            dst->Id = EntityId::FromUnderlying(src->EntityIndex);
            dst->x = src->x;
            dst->y = src->y;
            dst->z = src->z;
            dst->SpriteData.Width = src->SpriteWidth;
            dst->SpriteData.HeightMax = src->SpriteHeightPositive;
            dst->SpriteData.SpriteRect = ScreenRect(src->SpriteLeft, src->SpriteTop, src->SpriteRight, src->SpriteBottom);
            dst->Orientation = src->EntityDirection;
        }

        void ImportEntity(const RCT12EntityBase& src);

        std::string GetUserString(StringId stringId)
        {
            const auto originalString = _s6.CustomStrings[stringId % 1024];
            auto originalStringView = std::string_view(
                originalString, RCT12::GetRCTStringBufferLen(originalString, kUserStringMaxLength));
            auto asUtf8 = RCT2StringToUTF8(originalStringView, RCT2LanguageId::EnglishUK);
            auto justText = RCT12RemoveFormattingUTF8(asUtf8);
            return justText.data();
        }

        ObjectList GetRequiredObjects()
        {
            std::fill(std::begin(_pathToSurfaceMap), std::end(_pathToSurfaceMap), kObjectEntryIndexNull);
            std::fill(std::begin(_pathToQueueSurfaceMap), std::end(_pathToQueueSurfaceMap), kObjectEntryIndexNull);
            std::fill(std::begin(_pathToRailingMap), std::end(_pathToRailingMap), kObjectEntryIndexNull);

            ObjectList objectList;
            int objectIt = 0;
            ObjectEntryIndex surfaceCount = 0;
            ObjectEntryIndex railingCount = 0;
			
			auto& objectRepository = OpenRCT2::GetContext()->GetObjectRepository();
			std::vector<int> counts;
            for (int16_t objectType = EnumValue(ObjectType::ride); objectType <= EnumValue(ObjectType::water); objectType++)
			{
				counts.push_back(0);
			}
			
			unsigned int count = 0;
			/*for (unsigned int i = 0; i < _json["legacy_object_ids"].size(); i++, count++ )
			{
                rct_object_entry datEntry;
                cs.Read(&datEntry, sizeof(datEntry));
                ObjectEntryDescriptor desc(datEntry);
				//std::cout<<datEntry.GetName()<<"\n";
				
				auto identifier = _json["legacy_object_ids"][i]["id"].asString();
		        const ObjectRepositoryItem* ori = objectRepository.FindObjectLegacy(identifier);
		        if (ori == nullptr)
		        {
					std::cout << "Could not find object by legacy ID <"<<identifier<<">\n";
		        }
		        //const rct_object_entry* entry = &ori->ObjectEntry;
				
				ObjectEntryDescriptor entry(ori->ObjectEntry);
				
				auto objectType = _json["legacy_object_ids"][i]["type"].asUInt();
				//objectList.SetObject(counts[objectType - EnumValue(ObjectType::Ride)], entry);
				//counts[objectType - EnumValue(ObjectType::Ride)] += 1;
			}*/
			for (unsigned int i = 0; i < _json["object_ids"].size(); i++ )
			{
                ObjectEntryDescriptor desc;
                desc.Type = static_cast<ObjectType>(_json["object_ids"][i]["type"].asUInt()); //objectType;
                auto identifier = _json["object_ids"][i]["id"].asString(); // cs.Read<std::string>();
				//std::cout<<identifier<<"\n";
				
                desc.Identifier = identifier;
                //desc.Version = cs.Read<std::string>();

                objectList.SetObject(i, desc);
                //break;
				
				/*
				auto identifier = _json["object_ids"][i]["id"].asString();
		        const ObjectRepositoryItem* ori = objectRepository.FindObject(identifier);
		        if (ori == nullptr)
		        {
					std::cout << "Could not find object by ID <"<<identifier<<">\n";
		        }
		        //const rct_object_entry* entry = &ori->ObjectEntry;
				
				ObjectEntryDescriptor entry(ori->ObjectEntry);
				
				auto objectType = _json["object_ids"][i]["type"].asUInt();
                if (objectType == EnumValue(ObjectType::Paths))
				{
                    auto footpathMapping = GetFootpathSurfaceId(entry);
                    if (footpathMapping == nullptr)
                    {
                        // Unsupported footpath
                        objectList.SetObject(counts[objectType - EnumValue(ObjectType::Ride)], entry);
                    }
                    else
                    {
						auto c = counts[objectType - EnumValue(ObjectType::Ride)];
                        // We have surface objects for this footpath
                        auto surfaceIndex = objectList.Find(
                            ObjectType::FootpathSurface, footpathMapping->NormalSurface);
                        if (surfaceIndex == kObjectEntryIndexNull)
                        {
                            objectList.SetObject(
                                ObjectType::FootpathSurface, surfaceCount, footpathMapping->NormalSurface);
                            surfaceIndex = surfaceCount++;
                        }
                        _pathToSurfaceMap[c] = surfaceIndex;

                        surfaceIndex = objectList.Find(ObjectType::FootpathSurface, footpathMapping->QueueSurface);
                        if (surfaceIndex == kObjectEntryIndexNull)
                        {
                            objectList.SetObject(
                                ObjectType::FootpathSurface, surfaceCount, footpathMapping->QueueSurface);
                            surfaceIndex = surfaceCount++;
                        }
                        _pathToQueueSurfaceMap[c] = surfaceIndex;

                        auto railingIndex = objectList.Find(ObjectType::FootpathRailings, footpathMapping->Railing);
                        if (railingIndex == kObjectEntryIndexNull)
                        {
                            objectList.SetObject(ObjectType::FootpathRailings, railingCount, footpathMapping->Railing);
                            railingIndex = railingCount++;
                        }
                        _pathToRailingMap[c] = railingIndex;
                    }
				}
				else {
					objectList.SetObject(counts[objectType - EnumValue(ObjectType::Ride)], entry);					
				}
				counts[objectType - EnumValue(ObjectType::Ride)] += 1;*/
			}
			/*
            for (int16_t objectType = EnumValue(ObjectType::Ride); objectType <= EnumValue(ObjectType::Water); objectType++)
            {
                for (int16_t i = 0; i < rct2_object_entry_group_counts[objectType]; i++, objectIt++)
                {
					
					
                    auto entry = ObjectEntryDescriptor(_s6.Objects[objectIt]);
                    if (entry.HasValue())
                    {
                        if (objectType == EnumValue(ObjectType::Paths))
                        {
                            auto footpathMapping = GetFootpathSurfaceId(entry);
                            if (footpathMapping == nullptr)
                            {
                                // Unsupported footpath
                                objectList.SetObject(i, entry);
                            }
                            else
                            {
                                // We have surface objects for this footpath
                                auto surfaceIndex = objectList.Find(
                                    ObjectType::FootpathSurface, footpathMapping->NormalSurface);
                                if (surfaceIndex == kObjectEntryIndexNull)
                                {
                                    objectList.SetObject(
                                        ObjectType::FootpathSurface, surfaceCount, footpathMapping->NormalSurface);
                                    surfaceIndex = surfaceCount++;
                                }
                                _pathToSurfaceMap[i] = surfaceIndex;

                                surfaceIndex = objectList.Find(ObjectType::FootpathSurface, footpathMapping->QueueSurface);
                                if (surfaceIndex == kObjectEntryIndexNull)
                                {
                                    objectList.SetObject(
                                        ObjectType::FootpathSurface, surfaceCount, footpathMapping->QueueSurface);
                                    surfaceIndex = surfaceCount++;
                                }
                                _pathToQueueSurfaceMap[i] = surfaceIndex;

                                auto railingIndex = objectList.Find(ObjectType::FootpathRailings, footpathMapping->Railing);
                                if (railingIndex == kObjectEntryIndexNull)
                                {
                                    objectList.SetObject(ObjectType::FootpathRailings, railingCount, footpathMapping->Railing);
                                    railingIndex = railingCount++;
                                }
                                _pathToRailingMap[i] = railingIndex;
                            }
                        }
                        else
                        {
                            objectList.SetObject(i, entry);
                        }
                    }
                }
            }
			*/
            // Add default rct2 terrain surfaces and edges
            AddDefaultEntries();

            // Find if any rct1 terrain surfaces or edges have been used
            /*const bool hasRCT1Terrain = std::any_of(
                std::begin(_s6.tile_elements), std::end(_s6.tile_elements), [](RCT12TileElement& tile) {
                    auto* surface = tile.AsSurface();
                    if (surface == nullptr)
                    {
                        return false;
                    }
                    if (surface->GetSurfaceStyle() >= std::size(RCT2::DefaultTerrainSurfaces))
                    {
                        return true;
                    }
                    if (surface->GetEdgeStyle() >= std::size(RCT2::DefaultTerrainEdges))
                    {
                        return true;
                    }
                    return false;
                });
			*/
            // If an rct1 surface or edge then load all the Hybrid surfaces and edges
            //if (hasRCT1Terrain)
            {
                _terrainSurfaceEntries.AddRange(OpenRCT2HybridTerrainSurfaces);
                _terrainEdgeEntries.AddRange(OpenRCT2HybridTerrainEdges);
            }

            AppendRequiredObjects(objectList, ObjectType::terrainSurface, _terrainSurfaceEntries);
            AppendRequiredObjects(objectList, ObjectType::terrainEdge, _terrainEdgeEntries);
            RCT12AddDefaultObjects(objectList);
            return objectList;
        }
    };

    template<>
    void JsonImporter::ImportEntity<::Vehicle>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::Vehicle>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT2::Vehicle*>(&baseSrc);
        const auto& ride = _s6.Rides[src->Ride];

        ImportEntityCommonProperties(dst, src);
        dst->SubType = ::Vehicle::Type(src->Type);
        dst->Pitch = src->Pitch;
        dst->bank_rotation = src->BankRotation;
        dst->remaining_distance = src->RemainingDistance;
        dst->velocity = src->Velocity;
        dst->acceleration = src->Acceleration;
        dst->ride = RideId::FromUnderlying(src->Ride);
        dst->vehicle_type = src->VehicleType;
        dst->colours.Body = src->Colours.BodyColour;
        dst->colours.Trim = src->Colours.TrimColour;
        dst->colours.Tertiary = src->ColoursExtended;
        dst->track_progress = src->TrackProgress;
        dst->TrackLocation = { src->TrackX, src->TrackY, src->TrackZ };
        if (src->BoatLocation.IsNull() || static_cast<RideMode>(ride.mode) != RideMode::boatHire
            || src->Status != static_cast<uint8_t>(::Vehicle::Status::TravellingBoat))
        {
            dst->BoatLocation.SetNull();
            dst->SetTrackDirection(src->GetTrackDirection());
            // Skipping OriginalRideClass::WildMouse - this is handled specifically.
            auto originalClass = IsFlatRide(src->Ride) ? OriginalRideClass::FlatRide : OriginalRideClass::Regular;
            auto convertedType = RCT2TrackTypeToOpenRCT2(src->GetTrackType(), originalClass);
            dst->SetTrackType(convertedType);
            // RotationControlToggle and Booster are saved as the same track piece ID
            // Which one the vehicle is using must be determined
            if (src->GetTrackType() == OpenRCT2::RCT12::TrackElemType::RotationControlToggleAlias)
            {
                // Merging hacks mean the track type that's appropriate for the ride type is not necessarily the track type the
                // ride is on. It's possible to create unwanted behavior if a user layers spinning control track on top of
                // booster track but this is unlikely since only two rides have spinning control track - by default they load as
                // booster.
                TileElement* tileElement2 = MapGetTrackElementAtOfTypeSeq(
                    dst->TrackLocation, TrackElemType::RotationControlToggle, 0);

                if (tileElement2 != nullptr)
                    dst->SetTrackType(TrackElemType::RotationControlToggle);
            }
            else if (src->GetTrackType() == OpenRCT2::RCT12::TrackElemType::BlockBrakes)
            {
                dst->brake_speed = kRCT2DefaultBlockBrakeSpeed;
            }
        }
        else
        {
            dst->BoatLocation = TileCoordsXY{ src->BoatLocation.x, src->BoatLocation.y }.ToCoordsXY();
            dst->SetTrackDirection(0);
            dst->SetTrackType(OpenRCT2::TrackElemType::Flat);
        }

        dst->next_vehicle_on_train = EntityId::FromUnderlying(src->NextVehicleOnTrain);
        dst->prev_vehicle_on_ride = EntityId::FromUnderlying(src->PrevVehicleOnRide);
        dst->next_vehicle_on_ride = EntityId::FromUnderlying(src->NextVehicleOnRide);
        dst->var_44 = src->Var44;
        dst->mass = src->Mass;
        dst->Flags = src->UpdateFlags;
        dst->SwingSprite = src->SwingSprite;
        dst->current_station = StationIndex::FromUnderlying(src->CurrentStation);
        dst->current_time = src->CurrentTime;
        dst->crash_z = src->CrashZ;

        ::Vehicle::Status statusSrc = ::Vehicle::Status::MovingToEndOfStation;
        if (src->Status <= static_cast<uint8_t>(::Vehicle::Status::StoppedByBlockBrakes))
        {
            statusSrc = static_cast<::Vehicle::Status>(src->Status);
        }

        dst->status = statusSrc;
        dst->sub_state = src->SubState;
        for (size_t i = 0; i < std::size(src->Peep); i++)
        {
            dst->peep[i] = EntityId::FromUnderlying(src->Peep[i]);
            dst->peep_tshirt_colours[i] = src->PeepTshirtColours[i];
        }
        dst->num_seats = src->NumSeats;
        dst->num_peeps = src->NumPeeps;
        dst->next_free_seat = src->NextFreeSeat;
        dst->restraints_position = src->RestraintsPosition;
        dst->crash_x = src->CrashX;
        dst->sound2_flags = src->Sound2Flags;
        dst->spin_sprite = src->SpinSprite;
        dst->sound1_id = static_cast<OpenRCT2::Audio::SoundId>(src->Sound1Id);
        dst->sound1_volume = src->Sound1Volume;
        dst->sound2_id = static_cast<OpenRCT2::Audio::SoundId>(src->Sound2Id);
        dst->sound2_volume = src->Sound2Volume;
        dst->sound_vector_factor = src->SoundVectorFactor;
        dst->time_waiting = src->TimeWaiting;
        dst->speed = src->Speed;
        dst->powered_acceleration = src->PoweredAcceleration;
        dst->CollisionDetectionTimer = src->CollisionDetectionTimer;
        dst->animation_frame = src->AnimationFrame;
        dst->animationState = src->AnimationState;
        dst->scream_sound_id = static_cast<OpenRCT2::Audio::SoundId>(src->ScreamSoundId);
        dst->TrackSubposition = VehicleTrackSubposition{ src->TrackSubposition };
        dst->NumLaps = src->NumLaps;
        dst->brake_speed = src->BrakeSpeed;
        dst->lost_time_out = src->LostTimeOut;
        dst->vertical_drop_countdown = src->VerticalDropCountdown;
        dst->var_D3 = src->VarD3;
        dst->mini_golf_current_animation = MiniGolfAnimation(src->MiniGolfCurrentAnimation);
        dst->mini_golf_flags = src->MiniGolfFlags;
        dst->ride_subtype = RCTEntryIndexToOpenRCT2EntryIndex(src->RideSubtype);
        dst->seat_rotation = src->SeatRotation;
        dst->target_seat_rotation = src->TargetSeatRotation;
        if (src->Flags & RCT12_ENTITY_FLAGS_IS_CRASHED_VEHICLE_ENTITY)
        {
            dst->SetFlag(VehicleFlags::Crashed);
        }
        dst->BlockBrakeSpeed = kRCT2DefaultBlockBrakeSpeed;
    }

    static uint32_t AdjustScenarioToCurrentTicks(const S6Data& s6, uint32_t tick)
    {
        // Previously gScenarioTicks was used as a time point, now it's gCurrentTicks.
        // gCurrentTicks and gScenarioTicks are now exported as the same, older saves that have a different
        // scenario tick must account for the difference between the two.
        uint32_t ticksElapsed = s6.ScenarioTicks - tick;
        return s6.GameTicks1 - ticksElapsed;
    }

    template<>
    void JsonImporter::ImportEntity<::Guest>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::Guest>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const Peep*>(&baseSrc);
        ImportEntityPeep(dst, src);

        dst->OutsideOfPark = static_cast<bool>(src->OutsideOfPark);
        dst->GuestNumRides = src->NoOfRides;
        dst->Happiness = src->Happiness;
        dst->HappinessTarget = src->HappinessTarget;
        dst->Nausea = src->Nausea;
        dst->NauseaTarget = src->NauseaTarget;
        dst->Hunger = src->Hunger;
        dst->Thirst = src->Thirst;
        dst->Toilet = src->Toilet;
        dst->TimeToConsume = src->TimeToConsume;
        dst->Intensity = static_cast<IntensityRange>(src->Intensity);
        dst->NauseaTolerance = static_cast<PeepNauseaTolerance>(src->NauseaTolerance);
        dst->PaidOnDrink = src->PaidOnDrink;

        OpenRCT2::RideUse::GetHistory().Set(dst->Id, RCT12GetRidesBeenOn(src));
        OpenRCT2::RideUse::GetTypeHistory().Set(dst->Id, RCT12GetRideTypesBeenOn(src));

        dst->SetItemFlags(src->GetItemFlags());
        dst->Photo1RideRef = RCT12RideIdToOpenRCT2RideId(src->Photo1RideRef);
        dst->Photo2RideRef = RCT12RideIdToOpenRCT2RideId(src->Photo2RideRef);
        dst->Photo3RideRef = RCT12RideIdToOpenRCT2RideId(src->Photo3RideRef);
        dst->Photo4RideRef = RCT12RideIdToOpenRCT2RideId(src->Photo4RideRef);
        dst->GuestNextInQueue = EntityId::FromUnderlying(src->NextInQueue);
        dst->TimeInQueue = src->TimeInQueue;
        dst->CashInPocket = src->CashInPocket;
        dst->CashSpent = src->CashSpent;
        dst->ParkEntryTime = AdjustScenarioToCurrentTicks(_s6, src->ParkEntryTime);
        dst->RejoinQueueTimeout = src->RejoinQueueTimeout;
        dst->PreviousRide = RCT12RideIdToOpenRCT2RideId(src->PreviousRide);
        dst->PreviousRideTimeOut = src->PreviousRideTimeOut;
        for (size_t i = 0; i < std::size(src->Thoughts); i++)
        {
            auto srcThought = &src->Thoughts[i];
            auto dstThought = &dst->Thoughts[i];
            dstThought->type = static_cast<PeepThoughtType>(srcThought->Type);
            if (srcThought->Item == kRCT12PeepThoughtItemNone)
                dstThought->item = kPeepThoughtItemNone;
            else
                dstThought->item = srcThought->Item;
            dstThought->freshness = srcThought->Freshness;
            dstThought->fresh_timeout = srcThought->FreshTimeout;
        }
        dst->GuestHeadingToRideId = RCT12RideIdToOpenRCT2RideId(src->GuestHeadingToRideId);
        dst->GuestIsLostCountdown = src->PeepIsLostCountdown;
        dst->LitterCount = src->LitterCount;
        dst->GuestTimeOnRide = src->TimeOnRide;
        dst->DisgustingCount = src->DisgustingCount;
        dst->PaidToEnter = src->PaidToEnter;
        dst->PaidOnRides = src->PaidOnRides;
        dst->PaidOnFood = src->PaidOnFood;
        dst->PaidOnSouvenirs = src->PaidOnSouvenirs;
        dst->AmountOfFood = src->NoOfFood;
        dst->AmountOfDrinks = src->NoOfDrinks;
        dst->AmountOfSouvenirs = src->NoOfSouvenirs;
        dst->VandalismSeen = src->VandalismSeen;
        dst->VoucherType = src->VoucherType;
        dst->VoucherRideId = RCT12RideIdToOpenRCT2RideId(src->VoucherArguments);
        dst->SurroundingsThoughtTimeout = src->SurroundingsThoughtTimeout;
        dst->Angriness = src->Angriness;
        dst->TimeLost = src->TimeLost;
        dst->DaysInQueue = src->DaysInQueue;
        dst->BalloonColour = src->BalloonColour;
        dst->UmbrellaColour = src->UmbrellaColour;
        dst->HatColour = src->HatColour;
        dst->FavouriteRide = RCT12RideIdToOpenRCT2RideId(src->FavouriteRide);
        dst->FavouriteRideRating = src->FavouriteRideRating;
    }

    template<>
    void JsonImporter::ImportEntity<::Staff>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::Staff>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const Peep*>(&baseSrc);
        ImportEntityPeep(dst, src);

        dst->AssignedStaffType = StaffType(src->StaffType);
        dst->MechanicTimeSinceCall = src->MechanicTimeSinceCall;

        dst->HireDate = src->ParkEntryTime;
        dst->StaffOrders = src->StaffOrders;
        dst->StaffMowingTimeout = src->StaffMowingTimeout;
        dst->StaffLawnsMown = src->PaidToEnter;
        dst->StaffGardensWatered = src->PaidOnRides;
        dst->StaffLitterSwept = src->PaidOnFood;
        dst->StaffBinsEmptied = src->PaidOnSouvenirs;

        ImportStaffPatrolArea(dst, src->StaffId);
    }

    template<>
    void JsonImporter::ImportEntity<::SteamParticle>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::SteamParticle>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntitySteamParticle*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->time_to_move = src->TimeToMove;
        dst->frame = src->Frame;
    }

    template<>
    void JsonImporter::ImportEntity<::MoneyEffect>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::MoneyEffect>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntityMoneyEffect*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->MoveDelay = src->MoveDelay;
        dst->NumMovements = src->NumMovements;
        dst->GuestPurchase = src->Vertical;
        dst->Value = src->Value;
        dst->OffsetX = src->OffsetX;
        dst->Wiggle = src->Wiggle;
    }

    template<>
    void JsonImporter::ImportEntity<::VehicleCrashParticle>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::VehicleCrashParticle>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntityCrashedVehicleParticle*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->frame = src->Frame;
        dst->time_to_live = src->TimeToLive;
        dst->frame = src->Frame;
        dst->colour[0] = src->Colour[0];
        dst->colour[1] = src->Colour[1];
        dst->crashed_sprite_base = src->CrashedEntityBase;
        dst->velocity_x = src->VelocityX;
        dst->velocity_y = src->VelocityY;
        dst->velocity_z = src->VelocityZ;
        dst->acceleration_x = src->AccelerationX;
        dst->acceleration_y = src->AccelerationY;
        dst->acceleration_z = src->AccelerationZ;
    }

    template<>
    void JsonImporter::ImportEntity<::ExplosionCloud>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::ExplosionCloud>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntityParticle*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->frame = src->Frame;
    }

    template<>
    void JsonImporter::ImportEntity<::ExplosionFlare>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::ExplosionFlare>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntityParticle*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->frame = src->Frame;
    }

    template<>
    void JsonImporter::ImportEntity<::CrashSplashParticle>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::CrashSplashParticle>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntityParticle*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->frame = src->Frame;
    }

    template<>
    void JsonImporter::ImportEntity<::JumpingFountain>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::JumpingFountain>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntityJumpingFountain*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->NumTicksAlive = src->NumTicksAlive;
        dst->frame = src->Frame;
        dst->fountainFlags = src->fountainFlags;
        dst->TargetX = src->TargetX;
        dst->TargetY = src->TargetY;
        dst->Iteration = src->Iteration;
        dst->FountainType = RCT12MiscEntityType(src->Type) == RCT12MiscEntityType::JumpingFountainSnow
            ? ::JumpingFountainType::Snow
            : ::JumpingFountainType::Water;
    }

    template<>
    void JsonImporter::ImportEntity<::Balloon>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::Balloon>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntityBalloon*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->popped = src->Popped;
        dst->time_to_move = src->TimeToMove;
        dst->frame = src->Frame;
        dst->colour = src->Colour;
    }

    template<>
    void JsonImporter::ImportEntity<::Duck>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::Duck>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntityDuck*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->frame = src->Frame;
        dst->target_x = src->TargetX;
        dst->target_y = src->TargetY;
        dst->state = static_cast<::Duck::DuckState>(src->State);
    }

    template<>
    void JsonImporter::ImportEntity<::Litter>(const RCT12EntityBase& baseSrc)
    {
        auto dst = CreateEntityAt<::Litter>(EntityId::FromUnderlying(baseSrc.EntityIndex));
        auto src = static_cast<const RCT12EntityLitter*>(&baseSrc);
        ImportEntityCommonProperties(dst, src);
        dst->SubType = ::Litter::Type(src->Type);
        dst->creationTick = AdjustScenarioToCurrentTicks(_s6, src->CreationTick);
    }

    void JsonImporter::ImportEntity(const RCT12EntityBase& src)
    {
        switch (GetEntityTypeFromRCT2Sprite(&src))
        {
            case EntityType::Vehicle:
                ImportEntity<::Vehicle>(src);
                break;
            case EntityType::Guest:
                ImportEntity<::Guest>(src);
                break;
            case EntityType::Staff:
                ImportEntity<::Staff>(src);
                break;
            case EntityType::SteamParticle:
                ImportEntity<::SteamParticle>(src);
                break;
            case EntityType::MoneyEffect:
                ImportEntity<::MoneyEffect>(src);
                break;
            case EntityType::CrashedVehicleParticle:
                ImportEntity<::VehicleCrashParticle>(src);
                break;
            case EntityType::ExplosionCloud:
                ImportEntity<::ExplosionCloud>(src);
                break;
            case EntityType::ExplosionFlare:
                ImportEntity<::ExplosionFlare>(src);
                break;
            case EntityType::CrashSplash:
                ImportEntity<::CrashSplashParticle>(src);
                break;
            case EntityType::JumpingFountain:
                ImportEntity<::JumpingFountain>(src);
                break;
            case EntityType::Balloon:
                ImportEntity<::Balloon>(src);
                break;
            case EntityType::Duck:
                ImportEntity<::Duck>(src);
                break;
            case EntityType::Litter:
                ImportEntity<::Litter>(src);
                break;
            default:
                // Null elements do not need imported
                break;
        }
    }
} // namespace RCT2

std::unique_ptr<IParkImporter> ParkImporter::CreateJson(IObjectRepository& objectRepository)
{
    return std::make_unique<RCT2::JsonImporter>(objectRepository);
}

/*static void show_error(uint8_t errorType, rct_string_id errorStringId)
{
    if (errorType == ERROR_TYPE_GENERIC)
    {
        context_show_error(errorStringId, STR_NONE, {});
    }
    context_show_error(STR_UNABLE_TO_LOAD_FILE, errorStringId, {});
}
*/