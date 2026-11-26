/**
 * Every user-facing string for the route/report flow, English and Hindi, in one
 * table. Hindi needs review by a fluent speaker before recording (brief 13.3).
 */
import type { HazardStateName, ObservationKind } from "./contracts.ts";

export type Lang = "en" | "hi";

const STRINGS = {
  tagline: { en: "Recent water reports. Better route decisions.", hi: "ताज़ा जलभराव रिपोर्ट। बेहतर रास्ते का फ़ैसला।" },
  compare: { en: "Compare routes", hi: "रास्तों की तुलना करें" },
  report: { en: "Report conditions", hi: "स्थिति बताएं" },
  camera: { en: "Camera calibration", hi: "कैमरा कैलिब्रेशन" },
  startRide: { en: "Start ride", hi: "राइड शुरू करें" },
  preview: { en: "Preview route", hi: "रास्ता देखें" },
  why: { en: "Why this route?", hi: "यह रास्ता क्यों?" },
  coverage: { en: "Pilot coverage: selected corridor", hi: "पायलट कवरेज: चुना हुआ रास्ता" },
  geometryPending: { en: "Road geometry not yet human-reviewed", hi: "सड़क की बनावट अभी किसी इंसान ने नहीं जाँची" },
  take: { en: "Suggested", hi: "सुझाया गया" },
  avoid: { en: "Avoided", hi: "टाला गया" },
  available: { en: "Also possible", hi: "यह भी संभव" },
  noAlternative: {
    en: "No supported alternative found. Conditions need checking before travel.",
    hi: "कोई समर्थित वैकल्पिक रास्ता नहीं मिला। निकलने से पहले स्थिति जाँचें।",
  },
  noReports: {
    en: "No current waterlogging reports on the assessed segments.",
    hi: "जाँचे गए हिस्सों पर अभी जलभराव की कोई रिपोर्ट नहीं है।",
  },
  notSafetyClaim: {
    en: "This is not a safety guarantee. Roads outside the assessed underpass are not checked.",
    hi: "यह सुरक्षा की गारंटी नहीं है। जाँचे गए अंडरपास के बाहर की सड़कें नहीं देखी गईं।",
  },
  extra: { en: "Detour adds", hi: "चक्कर से अतिरिक्त" },
  staleWarning: {
    en: "Earlier reports have aged out and nobody has confirmed the road is clear. Still avoiding it.",
    hi: "पुरानी रिपोर्ट की समय-सीमा खत्म हो गई है, पर रास्ता साफ़ होने की पुष्टि नहीं हुई। अब भी इससे बचा जा रहा है।",
  },
  savedRoute: { en: "Saved route - not current. Reconnect to recheck.", hi: "सहेजा रास्ता - ताज़ा नहीं। दोबारा जाँचने के लिए कनेक्ट करें।" },
  outdated: { en: "Outdated - recalculation failed", hi: "पुराना - दोबारा गणना नहीं हो पाई" },
  newReport: { en: "New report received", hi: "नई रिपोर्ट मिली" },
  recalculated: { en: "Route recalculated", hi: "रास्ते की दोबारा गणना हुई" },
  offline: { en: "Offline · last synced", hi: "ऑफ़लाइन · आख़िरी सिंक" },
  neverSynced: { en: "never", hi: "कभी नहीं" },
  providerDown: { en: "Route comparison is unavailable right now.", hi: "अभी रास्तों की तुलना उपलब्ध नहीं है।" },
  outside: { en: "Outside the pilot corridor.", hi: "पायलट क्षेत्र से बाहर।" },
  queued: { en: "Queued reports", hi: "कतार में रिपोर्टें" },
  alertPhrase: {
    en: "Waterlogging has been reported ahead. Stop and check another route.",
    hi: "आगे जलभराव की रिपोर्ट है। रुक कर दूसरा रास्ता देखें।",
  },
  play: { en: "Play advisory", hi: "सलाह सुनें" },
  reviewTitle: { en: "We understood", hi: "हम समझ गए" },
  submit: { en: "Submit report", hi: "रिपोर्ट भेजें" },
  edit: { en: "Edit", hi: "बदलें" },
  next: { en: "Review", hi: "जाँचें" },
  back: { en: "Back", hi: "वापस" },
  minutesAgo: { en: "min ago", hi: "मिनट पहले" },
  justNow: { en: "just now", hi: "अभी" },
  sources: { en: "distinct sources", hi: "अलग स्रोत" },
  startNav: { en: "Preview route", hi: "रास्ता देखें" },
  stopNav: { en: "End preview", hi: "प्रीव्यू बंद करें" },
  share: { en: "Share trip", hi: "यात्रा साझा करें" },
  sos: { en: "SOS", hi: "SOS" },
  keepOriginal: { en: "Keep original route", hi: "पुराना रास्ता रखें" },
  acceptBypass: { en: "Accept bypass", hi: "बाईपास लें" },
  rerouteNotice: { en: "REROUTE NOTICE", hi: "रास्ता बदला" },
  bypassed: { en: "bypassed", hi: "टाला गया" },
  keptWarning: {
    en: "You chose the original route through reported water. Depth is unverified. Do not enter water.",
    hi: "आपने पानी की रिपोर्ट वाला पुराना रास्ता चुना। गहराई की पुष्टि नहीं है। पानी में न जाएं।",
  },
  tapHint: { en: "Tap the map to set a destination", hi: "मंज़िल चुनने के लिए नक्शे पर टैप करें" },
  tapStartHint: { en: "Tap the map to set the start", hi: "शुरुआत चुनने के लिए नक्शे पर टैप करें" },
  setStart: { en: "Set start on map", hi: "नक्शे पर शुरुआत सेट करें" },
  myLocation: { en: "Use my location", hi: "मेरी लोकेशन लें" },
  presetRoute: { en: "Preset route", hi: "तय रास्ता" },
  recenter: { en: "Re-center", hi: "बीच में लाएं" },
  simulated: { en: "Simulated drive · demo", hi: "सिम्युलेटेड ड्राइव · डेमो" },
  savdhaan: {
    en: "Caution! Waterlogging reported at Minto Bridge. Taking the flyover bypass.",
    hi: "सावधान! मिंटो ब्रिज पर जलभराव की रिपोर्ट है। फ्लाईओवर से बाईपास ले रहे हैं।",
  },
  autofill: { en: "Auto-fill from text", hi: "टेक्स्ट से ऑटो-फ़िल करें" },
  speak: { en: "Speak", hi: "बोलें" },
  depth: { en: "Water depth (your estimate)", hi: "पानी की गहराई (आपका अंदाज़ा)" },
  stalled: { en: "Stalled vehicles seen", hi: "फंसे वाहन दिखे" },
  rainContext: { en: "Rain (model)", hi: "बारिश (मॉडल)" },
  rainAdvisory: {
    en: "Heavy rain forecast near the corridor. No reports yet - conditions may change. Rain alone never closes a road here.",
    hi: "कॉरिडोर के पास भारी बारिश का पूर्वानुमान। अभी कोई रिपोर्ट नहीं - हालात बदल सकते हैं। यहाँ सिर्फ़ बारिश से रास्ता बंद नहीं होता।",
  },
  cameraAvoid: { en: "Avoiding water your camera flagged - only for you, for 20 min.", hi: "आपके कैमरे ने जो पानी देखा उससे बचाव - सिर्फ़ आपके लिए, 20 मिनट।" },
  clear: { en: "Clear", hi: "हटाएं" },
  demoWater: { en: "Demo: camera sees water at the underpass", hi: "डेमो: कैमरे को अंडरपास पर पानी दिखा" },
  layoutAuto: { en: "Auto", hi: "ऑटो" },
  layoutPhone: { en: "Phone", hi: "फ़ोन" },
  layoutCar: { en: "Car", hi: "कार" },
  // ride planner screens (static text in index.html, data-i18n*); Hindi drafted with Covexcode, reviewed
  p_overview: { en: "Overview", hi: "अवलोकन" },
  p_cancel: { en: "Cancel", hi: "रद्द करें" },
  p_re_center: { en: "Re-center", hi: "फिर केंद्रित करें" },
  p_report_issue: { en: "Report issue", hi: "समस्या रिपोर्ट करें" },
  p_get_there_with_kestrel: { en: "GET THERE WITH KESTREL", hi: "KESTREL के साथ पहुंचें" },
  p_plan_your_ride: { en: "Plan your ride", hi: "अपनी राइड प्लान करें" },
  p_a_familiar_route_a_little: { en: "A familiar route. A little more peace of mind.", hi: "जाना-पहचाना रास्ता। थोड़ा सा सुकून।" },
  p_from: { en: "From", hi: "से" },
  p_planning_as: { en: "Planning as", hi: "प्लानिंग:" },
  p_change: { en: "Change", hi: "बदलें" },
  p_details_reports_sharing: { en: "Details, reports & sharing", hi: "विवरण, रिपोर्ट और शेयरिंग" },
  p_calibration_queued_reports: { en: "Calibration & queued reports", hi: "कैलिब्रेशन और क्यू में रिपोर्ट" },
  p_report_a_civic_issue: { en: "+ Report a civic issue", hi: "+ नागरिक समस्या रिपोर्ट करें" },
  p_routes_consider_reported_hazards_conditions: { en: "Routes consider reported hazards. Conditions can change; stay aware as you travel. Map data © OpenStreetMap contributors.", hi: "रास्ते रिपोर्ट किए गए खतरों को ध्यान में रखते हैं। हालात बदल सकते हैं; सफर करते समय सतर्क रहें। मैप डेटा © OpenStreetMap योगदानकर्ता।" },
  p_kestrel_travel_profile: { en: "KESTREL / TRAVEL PROFILE", hi: "KESTREL / यात्रा प्रोफ़ाइल" },
  p_back_to_planner: { en: "← Back to planner", hi: "← प्लानर पर वापस" },
  p_how_are_you_travelling_today: { en: "How are you travelling today?", hi: "आज आप कैसे सफर कर रहे हैं?" },
  p_we_use_this_to_pick: { en: "We use this to pick your vehicle and how routes are explained. You can change it any time.", hi: "इससे हम आपकी गाड़ी चुनते हैं और रास्ते कैसे समझाए जाएं। आप इसे कभी भी बदल सकते हैं।" },
  p_two_wheeler_rider: { en: "Two-wheeler rider", hi: "दोपहिया चालक" },
  p_bike_or_scooter_underpasses_with: { en: "Bike or scooter. Underpasses with reported water are always avoided. Camera ride available.", hi: "बाइक या स्कूटर। रिपोर्ट किए गए पानी वाले अंडरपास से हमेशा बचा जाता है। कैमरा राइड उपलब्ध है।" },
  p_car_or_cab_driver: { en: "Car or cab driver", hi: "कार या कैब चालक" },
  p_route_around_reported_waterlogging_with: { en: "Route around reported waterlogging, with the time it costs.", hi: "रिपोर्ट किए गए जलभराव से बचाकर रास्ता, और उसमें लगने वाला समय।" },
  p_auto_rickshaw_driver: { en: "Auto-rickshaw driver", hi: "ऑटो-रिक्शा चालक" },
  p_low_clearance_reported_water_is: { en: "Low clearance: reported water is avoided.", hi: "कम क्लीयरेंस: रिपोर्ट किए गए पानी से बचा जाता है।" },
  p_commuter_planning_a_trip: { en: "Commuter planning a trip", hi: "सफर प्लान करने वाला यात्री" },
  p_check_the_route_before_you: { en: "Check the route before you leave.", hi: "निकलने से पहले रास्ता देख लें।" },
  p_community_reporter: { en: "Community reporter", hi: "कम्युनिटी रिपोर्टर" },
  p_report_water_you_can_see: { en: "Report water you can see from a safe place.", hi: "सुरक्षित जगह से दिख रहा पानी रिपोर्ट करें।" },
  p_no_account_no_location_needed: { en: "No account, no location needed to plan. Camera and GPS are asked for only when you start a ride.", hi: "प्लान करने के लिए खाता या लोकेशन ज़रूरी नहीं। कैमरा और GPS सिर्फ राइड शुरू करते समय मांगे जाते हैं।" },
  p_kestrel_choose_a_place: { en: "KESTREL / CHOOSE A PLACE", hi: "KESTREL / जगह चुनें" },
  p_search: { en: "Search", hi: "खोजें" },
  p_use_my_location: { en: "Use my location", hi: "मेरी लोकेशन लें" },
  p_pick_on_map: { en: "Pick on map", hi: "नक्शे पर चुनें" },
  p_popular_places: { en: "Popular places", hi: "लोकप्रिय जगहें" },
  p_search_covers_delhi_start_typing: { en: "Search covers Delhi: start typing a place, area, metro station or landmark. Place data © OpenStreetMap contributors (Photon, Nominatim).", hi: "खोज में दिल्ली शामिल है: जगह, इलाका, मेट्रो स्टेशन या लैंडमार्क टाइप करना शुरू करें। जगहों का डेटा © OpenStreetMap योगदानकर्ता (Photon, Nominatim)।" },
  p_kestrel_road_conditions: { en: "KESTREL / ROAD CONDITIONS", hi: "KESTREL / सड़क की हालत" },
  p_report_only_while_stopped_somewhere: { en: "Report only while stopped somewhere safe. Never go into water to check it.", hi: "सिर्फ किसी सुरक्षित जगह रुककर ही रिपोर्ट करें। पानी जांचने के लिए कभी पानी में न जाएं।" },
  p_text_is_sent_to_the: { en: "Text is sent to the server and its language model (Covexcode) to understand it. Your location is not collected - you pick the place.", hi: "टेक्स्ट समझने के लिए सर्वर और उसके भाषा मॉडल (Covexcode) को भेजा जाता है। आपकी लोकेशन नहीं ली जाती - जगह आप चुनते हैं।" },
  p_kestrel_route_details: { en: "KESTREL / ROUTE DETAILS", hi: "KESTREL / रास्ते की जानकारी" },
  p_kestrel_get_help: { en: "KESTREL / GET HELP", hi: "KESTREL / मदद लें" },
  p_emergency_and_breakdown_help: { en: "Emergency and breakdown help", hi: "इमरजेंसी और गाड़ी खराब होने पर मदद" },
  p_calls_go_through_your_phone: { en: "Calls go through your phone's dialer. Public Indian / Delhi helplines - verify locally before relying on them.", hi: "कॉल आपके फोन के डायलर से जाते हैं। भारतीय / दिल्ली की सार्वजनिक हेल्पलाइनें - भरोसा करने से पहले स्थानीय रूप से जांच लें।" },
  p_stuck_near_water_switch_off: { en: "Stuck near water: switch off the engine, do not restart a stalled engine in water, move to higher ground.", hi: "पानी के पास फंसे हैं: इंजन बंद करें, पानी में बंद इंजन को दोबारा स्टार्ट न करें, ऊंची जगह पर जाएं।" },
  p_potholes_seen: { en: "potholes seen", hi: "गड्ढे दिखे" },
  p_re_centre_on_me: { en: "Re-centre on me", hi: "मुझ पर फिर केंद्रित करें" },
  p_save_clip: { en: "Save clip", hi: "क्लिप सेव करें" },
  p_calibrate: { en: "Calibrate", hi: "कैलिब्रेट करें" },
  p_end_ride: { en: "End ride", hi: "राइड खत्म करें" },
  p_kestrel_your_journey: { en: "KESTREL / YOUR JOURNEY", hi: "KESTREL / आपका सफर" },
  p_your_journey_at_a_glance: { en: "YOUR JOURNEY, AT A GLANCE", hi: "आपका सफर, एक नज़र में" },
  p_ride_summary: { en: "Ride summary", hi: "राइड सारांश" },
  p_your_trip_the_road_conditions: { en: "Your trip, the road conditions, and the moments you saved.", hi: "आपका सफर, सड़क की हालत, और आपके सेव किए पल।" },
  p_duration: { en: "Duration", hi: "समय" },
  p_distance: { en: "Distance", hi: "दूरी" },
  p_potholes_detected: { en: "Potholes detected", hi: "गड्ढे मिले" },
  p_warnings_given: { en: "Warnings given", hi: "चेतावनियां दी गईं" },
  p_possible_water_camera_cue: { en: "Possible water (camera cue)", hi: "पानी हो सकता है (कैमरा संकेत)" },
  p_the_camera_flagged_possible_water: { en: "The camera flagged possible water on this ride. It is an experimental cue and can be wrong (wet road, shadow, glare).\n          If you saw water yourself, report it - your report is what changes routes for others.", hi: "कैमरा ने इस राइड में पानी होने का संकेत दिया। यह एक प्रयोगात्मक संकेत है और गलत हो सकता है (गीली सड़क, छाया, चमक)। अगर आपने खुद पानी देखा है, तो रिपोर्ट करें - आपकी रिपोर्ट से ही दूसरों के रास्ते बदलते हैं।" },
  p_report_water_i_saw: { en: "Report water I saw", hi: "मैंने जो पानी देखा, रिपोर्ट करें" },
  p_saved_footage_in_memory_download: { en: "Saved footage (in memory - download to keep)", hi: "सेव की गई फुटेज (मेमोरी में - रखने के लिए डाउनलोड करें)" },
  p_no_incidents_saved_this_ride: { en: "No incidents saved this ride.", hi: "इस राइड में कोई घटना सेव नहीं हुई।" },
  p_done: { en: "Done", hi: "हो गया" },
  p_kestrel_preferences: { en: "KESTREL / PREFERENCES", hi: "KESTREL / सेटिंग्स" },
  p_back: { en: "← Back", hi: "← वापस" },
  p_make_it_work_for_your: { en: "MAKE IT WORK FOR YOUR RIDE", hi: "अपनी राइड के हिसाब से सेट करें" },
  p_camera_ride_settings: { en: "Camera & ride settings", hi: "कैमरा और राइड सेटिंग्स" },
  p_set_up_your_camera_tune: { en: "Set up your camera, tune warnings, and choose what to share.", hi: "अपना कैमरा सेट करें, चेतावनियां ट्यून करें और तय करें क्या शेयर करना है।" },
  p_check_your_camera: { en: "Check your camera", hi: "अपना कैमरा जांचें" },
  p_how_camera_estimates_work: { en: "How camera estimates work", hi: "कैमरा अनुमान कैसे काम करते हैं" },
  p_the_camera_uses_pothole_detection: { en: "The camera uses pothole detection and water segmentation. Distance and depth estimates assume a flat road; calibrate them to your bike and phone mount.", hi: "कैमरा गड्ढों की पहचान और पानी की पहचान (सेगमेंटेशन) का इस्तेमाल करता है। दूरी और गहराई के अनुमान सपाट सड़क मानकर लगाए जाते हैं; इन्हें अपनी बाइक और फोन माउंट के हिसाब से कैलिब्रेट करें।" },
  p_camera_calibration: { en: "Camera calibration", hi: "कैमरा कैलिब्रेशन" },
  p_match_these_values_to_your: { en: "Match these values to your phone mount.", hi: "इन वैल्यू को अपने फोन माउंट से मिलाएं।" },
  p_warnings_recording: { en: "Warnings & recording", hi: "चेतावनियां और रिकॉर्डिंग" },
  p_voice_sharing: { en: "Voice & sharing", hi: "आवाज़ और शेयरिंग" },
  p_changes_are_saved_automatically_on: { en: "Changes are saved automatically on this device.", hi: "बदलाव इस डिवाइस पर अपने आप सेव हो जाते हैं।" },
  p_route_map: { en: "Route map", hi: "रास्ते का नक्शा" },
  p_back_to_overview: { en: "Back to overview", hi: "अवलोकन पर वापस" },
  p_ride_mode: { en: "Ride mode", hi: "राइड मोड" },
  p_next_maneuver_tap_for_all: { en: "Next maneuver - tap for all steps", hi: "अगला मोड़ - सारे स्टेप देखने के लिए टैप करें" },
  p_lane_guidance: { en: "Lane guidance", hi: "लेन गाइडेंस" },
  p_route_planner: { en: "Route planner", hi: "रूट प्लानर" },
  p_choose_your_journey: { en: "Choose your journey", hi: "अपना सफर चुनें" },
  p_start_and_destination: { en: "Start and destination", hi: "शुरुआत और मंज़िल" },
  p_use_my_current_location_as: { en: "Use my current location as start", hi: "मेरी मौजूदा लोकेशन को शुरुआत बनाएं" },
  p_swap_start_and_destination: { en: "Swap start and destination", hi: "शुरुआत और मंज़िल बदलें" },
  p_travel_preferences: { en: "Travel preferences", hi: "सफर की पसंद" },
  p_vehicle: { en: "Vehicle", hi: "गाड़ी" },
  p_route_options: { en: "Route options", hi: "रास्ते के विकल्प" },
  p_choose_how_you_travel: { en: "Choose how you travel", hi: "आप कैसे सफर करते हैं चुनें" },
  p_back_to_route_planner: { en: "Back to route planner", hi: "रूट प्लानर पर वापस" },
  p_choose_a_place: { en: "Choose a place", hi: "जगह चुनें" },
  p_search_a_place_in_delhi: { en: "Search a place in Delhi", hi: "दिल्ली में जगह खोजें" },
  p_report_conditions: { en: "Report conditions", hi: "हालात रिपोर्ट करें" },
  p_e_g_minto_bridge_ke: { en: "e.g. Minto Bridge ke neeche 3 foot paani bhara hai", hi: "जैसे मिंटो ब्रिज के नीचे 3 फुट पानी भरा है" },
  p_why_this_route: { en: "Why this route", hi: "यह रास्ता क्यों" },
  p_emergency: { en: "Emergency", hi: "इमरजेंसी" },
  // planner chrome rendered by code or around nested markup
  soundOn: { en: "Sound on", hi: "आवाज़ चालू" },
  soundOff: { en: "Sound off", hi: "आवाज़ बंद" },
  chooseStartPoint: { en: "Choose starting point", hi: "शुरुआत की जगह चुनें" },
  chooseDest: { en: "Choose destination", hi: "मंज़िल चुनें" },
  hintPickDest: { en: "Choose a destination above to see your route.", hi: "अपना रास्ता देखने के लिए ऊपर मंज़िल चुनें।" },
  hintPickStart: { en: "Choose a starting point above, or use GPS for your current location.", hi: "ऊपर शुरुआत की जगह चुनें, या अपनी मौजूदा लोकेशन के लिए GPS इस्तेमाल करें।" },
  gpsUnavailable: { en: "GPS is unavailable. You can still choose your starting point on the map or search for a place.", hi: "GPS उपलब्ध नहीं है। आप फिर भी नक्शे पर शुरुआत की जगह चुन सकते हैं या कोई जगह खोज सकते हैं।" },
  roleRider: { en: "Two-wheeler rider", hi: "दोपहिया चालक" },
  roleDriver: { en: "Car or cab driver", hi: "कार या कैब चालक" },
  roleAuto: { en: "Auto-rickshaw driver", hi: "ऑटो-रिक्शा चालक" },
  roleCommuter: { en: "Commuter planning a trip", hi: "सफर प्लान करने वाला यात्री" },
  roleReporter: { en: "Community reporter", hi: "कम्युनिटी रिपोर्टर" },
  stepWhere: { en: "Where are you headed?", hi: "आप कहाँ जा रहे हैं?" },
  stepHow: { en: "How are you travelling?", hi: "आप कैसे जा रहे हैं?" },
  stepRoute: { en: "Your route", hi: "आपका रास्ता" },
  minimize: { en: "Minimize", hi: "छोटा करें" },
  toKey: { en: "To", hi: "तक" },
  modeCamera: { en: "Camera", hi: "कैमरा" },
  modePocket: { en: "Pocket", hi: "जेब में" },
} as const;

export const VEHICLE_LABEL: Record<string, Record<Lang, string>> = {
  two_wheeler: { en: "Two-wheeler", hi: "दोपहिया" },
  auto: { en: "Auto", hi: "ऑटो" },
  car: { en: "Car", hi: "कार" },
  suv: { en: "SUV", hi: "SUV" },
  ev: { en: "EV", hi: "EV" },
};

/** Shown when a restriction is active. No vehicle is cleared through reported water. */
export const VEHICLE_BADGE: Record<string, Record<Lang, string>> = {
  two_wheeler: { en: "Underpass bypass active for two-wheelers", hi: "दोपहिया के लिए अंडरपास बाईपास चालू है" },
  auto: { en: "Auto-safe corridor: underpass avoided", hi: "ऑटो के लिए अंडरपास टाला गया" },
  car: { en: "Avoiding reported water at the underpass", hi: "अंडरपास पर रिपोर्ट किए गए पानी से बचाव" },
  suv: {
    en: "High clearance does not override reports - depth is unverified, underpass still avoided",
    hi: "गाड़ी की ऊँचाई रिपोर्ट को दरकिनार नहीं करती - गहराई अपुष्ट है, अंडरपास फिर भी टाला गया।",
  },
  ev: { en: "EV battery protection: underpass avoided", hi: "EV बैटरी सुरक्षा: अंडरपास टाला गया" },
};

export const DEPTH_LABEL: Record<string, Record<Lang, string>> = {
  ankle: { en: "Ankle (<15 cm)", hi: "टखने तक (<15 cm)" },
  knee: { en: "Knee (15–30 cm)", hi: "घुटने तक (15–30 cm)" },
  waist: { en: "Waist (30–45 cm)", hi: "कमर तक (30–45 cm)" },
  submerged: { en: "Submerged (>45 cm)", hi: "डूबा हुआ (>45 cm)" },
};

export type Key = keyof typeof STRINGS;

export const STATE_LABEL: Record<HazardStateName, Record<Lang, string>> = {
  UNKNOWN: { en: "No current reports", hi: "कोई ताज़ा रिपोर्ट नहीं" },
  REPORTED: { en: "Reported", hi: "रिपोर्ट किया गया" },
  CORROBORATED: { en: "Corroborated", hi: "पुष्टि (कई स्रोत)" },
  CONFLICTED: { en: "Conflicting reports", hi: "परस्पर विरोधी रिपोर्टें" },
  STALE: { en: "Stale - unresolved", hi: "पुरानी - अनसुलझी" },
  RECENTLY_CLEAR_REPORTED: { en: "Recently reported clear", hi: "हाल में साफ़ बताया गया" },
};

export const STATE_EXPLAIN: Record<HazardStateName, Record<Lang, string>> = {
  UNKNOWN: { en: "No adequate recent evidence. Unknown is not the same as dry.", hi: "पर्याप्त ताज़ा सबूत नहीं। अज्ञात होना सूखा होना नहीं है।" },
  REPORTED: { en: "One fresh report of water or blockage. Avoided as a precaution.", hi: "पानी या रुकावट की एक ताज़ा रिपोर्ट। सावधानी के लिए टाला गया।" },
  CORROBORATED: { en: "Two or more separate contributors agree. This is agreement, not physical verification.", hi: "दो या ज़्यादा अलग लोग सहमत हैं। यह सहमति है, भौतिक पुष्टि नहीं।" },
  CONFLICTED: { en: "Newer reports disagree. Still avoided until a reviewer checks.", hi: "नई रिपोर्टों में असहमति है। समीक्षक के जाँचने तक अभी भी टाला गया।" },
  STALE: { en: "Water was reported earlier; no recent reports either way. Not treated as clear.", hi: "पहले पानी बताया गया था; अब किसी भी तरह की ताज़ा रिपोर्ट नहीं। साफ़ नहीं माना गया।" },
  RECENTLY_CLEAR_REPORTED: { en: "A community reviewer accepted two newer no-water reports. Not official clearance.", hi: "सामुदायिक समीक्षक ने 'पानी नहीं' की दो नई रिपोर्टें स्वीकार कीं। यह आधिकारिक मंज़ूरी नहीं है।" },
};

export const KIND_LABEL: Record<ObservationKind, Record<Lang, string>> = {
  WATER_OBSERVED: { en: "Water on the road", hi: "सड़क पर पानी" },
  ROAD_BLOCKED_REPORTED: { en: "Road blocked", hi: "रास्ता बंद" },
  NO_WATER_OBSERVED: { en: "No water seen", hi: "पानी नहीं दिखा" },
  UNSURE: { en: "Not sure", hi: "पक्का नहीं" },
};

export const REASON_LABEL: Record<string, Record<Lang, string>> = {
  CROSSES_RESTRICTED_HOTSPOT: { en: "passes through the affected underpass", hi: "प्रभावित अंडरपास से गुज़रता है" },
  AMBIGUOUS_ROAD_LEVEL: { en: "road level at the crossing is unverified", hi: "क्रॉसिंग पर सड़क का स्तर अपुष्ट" },
  RIDER_CAMERA_WATER: { en: "your camera flagged possible water here", hi: "आपके कैमरे ने यहाँ पानी होने की संभावना बताई" },
};

let lang: Lang = "en";
try {
  if (localStorage.getItem("kestrel.lang") === "hi") lang = "hi";
} catch {
  /* storage blocked: default English */
}

export const getLang = (): Lang => lang;

export function setLang(next: Lang): void {
  lang = next;
  document.documentElement.lang = next;
  try {
    localStorage.setItem("kestrel.lang", next);
  } catch {
    /* not fatal */
  }
}

export const t = (key: Key): string => STRINGS[key][lang];
export const pick = (table: Record<string, Record<Lang, string>>, key: string): string => table[key]?.[lang] ?? key;

/** "3 min ago" from an ISO time and the server-relative now. */
export function age(isoTime: string | null, nowMs: number): string {
  if (!isoTime) return "—";
  const minutes = Math.floor((nowMs - Date.parse(isoTime)) / 60_000);
  return minutes < 1 ? t("justNow") : `${minutes} ${t("minutesAgo")}`;
}

/**
 * Spoken ride alerts, English and Hindi (Devanagari for the voice, Hinglish
 * phonetic kept for review). `{name}` / `{m}` are filled in by alertText.
 * Camera water is always "possible": the cue is a heuristic, never a claim.
 */
export const ALERTS = {
  WATER_AHEAD: {
    en: { text: "Possible water ahead - slow down", spoken: "Caution. Possible water ahead. Slow down." },
    hi: { text: "आगे पानी हो सकता है - धीरे चलें", spoken: "सावधान! आगे पानी हो सकता है। धीरे चलें।", phonetic: "Savdhaan! Aage paani ho sakta hai. Dheere chalein." },
  },
  WATER_REROUTE: {
    en: { text: "Possible water ahead - finding a way around", spoken: "Caution. Possible water ahead. Finding a route around it." },
    hi: { text: "आगे पानी हो सकता है - नया रास्ता", spoken: "सावधान! आगे पानी हो सकता है। नया रास्ता चुना जा रहा है।", phonetic: "Savdhaan! Aage paani ho sakta hai. Naya raasta chuna ja raha hai." },
  },
  DEEP_POTHOLE: {
    en: { text: "Deep pothole in your lane", spoken: "Caution. Deep pothole ahead in your lane. Slow down." },
    hi: { text: "आपकी लेन में गहरा गड्ढा", spoken: "सावधान! आगे आपकी लेन में गहरा गड्ढा है। गति धीमी करें।", phonetic: "Savdhaan! Aage gehra gaddha hai. Speed dheemi karein." },
  },
  POTHOLE: {
    en: { text: "Pothole ahead", spoken: "Pothole ahead, {m} metres." },
    hi: { text: "आगे गड्ढा", spoken: "आगे गड्ढा, {m} मीटर।", phonetic: "Aage gaddha, {m} meter." },
  },
  HOTSPOT_REPORTED: {
    en: { text: "Water reported at {name}", spoken: "Caution. Waterlogging reported at {name}. Do not enter water." },
    hi: { text: "{name} पर पानी की रिपोर्ट", spoken: "सावधान! {name} पर जलभराव की रिपोर्ट है। पानी में न जाएं।", phonetic: "Savdhaan! {name} par jalbharaav ki report hai." },
  },
  ROUTE_UPDATED: {
    en: { text: "Route updated", spoken: "Route updated." },
    hi: { text: "रास्ता बदला गया", spoken: "रास्ता बदला गया।", phonetic: "Raasta badla gaya." },
  },
  RIDE_CAMERA: {
    en: { text: "Camera mode", spoken: "Ride started. Watching the road." },
    hi: { text: "कैमरा मोड", spoken: "राइड शुरू। कैमरा सड़क देख रहा है।", phonetic: "Ride shuru. Camera sadak dekh raha hai." },
  },
  RIDE_POCKET: {
    en: { text: "Pocket mode - camera off, voice guidance on", spoken: "Pocket mode. Camera off. Voice guidance on." },
    hi: { text: "पॉकेट मोड - कैमरा बंद, आवाज़ से रास्ता", spoken: "पॉकेट मोड। कैमरा बंद। आवाज़ से रास्ता बताया जाएगा।", phonetic: "Pocket mode. Camera band." },
  },
  ARRIVED: {
    en: { text: "You have arrived", spoken: "You have arrived." },
    hi: { text: "आप पहुँच गए", spoken: "आप मंज़िल पर पहुँच गए।", phonetic: "Aap manzil par pahunch gaye." },
  },
} as const;

export type AlertKey = keyof typeof ALERTS;

export function alertText(key: AlertKey, vars: Record<string, string | number> = {}): { text: string; spoken: string; voiceLang: string } {
  const a = ALERTS[key][lang];
  const fill = (s: string) => s.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? ""));
  return { text: fill(a.text), spoken: fill(a.spoken), voiceLang: lang === "hi" ? "hi-IN" : "en-IN" };
}
