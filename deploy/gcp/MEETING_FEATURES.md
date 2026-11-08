# Using Charcha in a group call

The host creates a meeting and shares its code. Each participant signs in, chooses their speaking and listening language, reviews the audio processing notice and requests admission. After admission, connect audio and unmute. Camera sharing is optional.

- Hosted rooms start with **VoiceShield off**. The admitted host can open **VoiceShield → Turn on VoiceShield** or turn it off during a call. Participants see the setting in the room and accept the host-controlled screening notice before joining. Monitoring gathers about four seconds of original audio per window on the server CPU while audio continues. Turning it off clears the current assessments. Earlier observations remain in the room's limited in-memory diagnostic history. A flag invites review. Scores have not been calibrated for Indian meeting speech.
- Open **Performance** on the meeting stage for this listener's network measurements and server translation times per language direction. **Play test tone** sends a one-second tone only to your browser and times its arrival. The detailed report opens separately while the meeting continues. For physical speech-end to listener playback, open the reviewed JSON from the offline capture guide on the detailed report. The file stays in the tab.
- In interpreted rooms, enable captions and use the transcript to correct or confirm details. Listeners sharing a target language share the translated output. Same-language listeners receive original speech.

In a live workspace, the host chooses **Live interpretation** or **Original audio** on the home page before creating the room. Original-audio meetings work across language choices with speech providers disabled. A separately opened Performance tab can use the most recent active seat for its signed-in browser session. Network round-trip time uses the WebRTC connection, including when muted. Incoming jitter and loss need received audio packets; translation-stage times need a completed interpreted delivery.

## Existing Delhi deployment

Run from the updated project checkout on the meeting server. Preserve the existing private bundle, identity database and usage ledger. Prepare the model once with `python3 scripts/fetch_audio_screening_model.py` if the pinned weights and license are missing. The screened image checks the model checksum and loads the classifier during its build.

For an existing identity database, run `python3 scripts/configure_identity_logout.py --apply` from the checkout containing the private bundle after the updated API is healthy. This sets the web client's signed logout notification endpoint and its exact return address. New realm imports include both settings. To switch accounts, select **Sign out**, confirm on the identity page, then select **Continue with Google**. **Clear previous sign-in** on the entry page also ends a remaining identity session after a timed-out or older app login.

For original audio plus VoiceShield, prepare the feature settings:

```sh
python3 scripts/prepare_meeting_features.py --bundle deploy/gcp/generated
```

For multilingual interpretation plus VoiceShield, use the following command instead. The private file supplies `GNANI_API_KEY`, `EVON_BASE_URL` and `EVON_MODEL`, plus a bearer key or Modal proxy credentials when the endpoint requires them. It may set the supported provider rates and daily caps. Keep it outside the build context or in an ignored private directory. An available Evon endpoint and sufficient provider concurrency are required for live interpretation.

```sh
python3 scripts/prepare_meeting_features.py --bundle deploy/gcp/generated --providers /private/path/providers.env
```

Between meetings, apply the selected settings and updated UI with Docker Compose:

```sh
docker compose -f deploy/gcp/generated/compose.json -f deploy/gcp/meeting.compose.yaml up -d --build api web
```

An API restart ends active room sessions. The overlay uses the existing login, media credentials and database volumes. Reapplying the original Compose file without the overlay restores the original operating mode.

Live speech requires a separate bounded operator grant for the meeting code. Only one grant can be active across the workspace at once. Other meetings can still use free features. After the host creates a room, copy the 12-character code from its invitation. In the same Compose project, `exec api python -m scripts.provider_flow status` shows the ledger.

For example, to **plan** one short interpreted turn with one target language, substitute the actual meeting code in this command. Planning makes no provider request and opens no grant.

```sh
docker compose -f deploy/gcp/generated/compose.json -f deploy/gcp/meeting.compose.yaml exec api python -m scripts.provider_flow plan --purpose live_interpretation --room-code MEETING_CODE --seconds 60 --stt-connections 1 --stt-seconds 15 --mt-requests 1 --mt-characters 200 --tts-requests 1 --tts-characters 300
```

Review the exact limits with the owner. Only after approval, use `approve` in place of `plan`, with the same arguments and `--human-approved`. Close the window with `close --flow-id ID` immediately after the turn. For multiple languages and speakers, plan recognition connections for overlapping speakers and translation/synthesis requests per distinct target language per turn. Speech queued under an earlier grant cannot draw from its replacement.

## Local run and verification

`npm run dev:shield` launches original audio and monitoring. With identity and speech providers configured, `npm run dev:meeting` launches interpreted rooms with monitoring and the same per-flow approval requirement. Install the server's `screening` extra and the pinned model first.

For five people speaking at the same time locally, the operator must allow five concurrent recognition connections (`USAGE_MAX_CONCURRENT_STT=5`) in the private server settings and budget for them in the approved flow. A lower configured limit still applies. Use the in-room connection status before unmuting.

To verify the combined path independently of provider access, run the following with the project Python environment and the local LiveKit binary installed:

```sh
python scripts/verify_group_conference.py --monitor --output work/group-screening-run.json
```

Use a fresh output filename for each run. Five synthetic speakers publish overlapping microphone tracks. A sixth participant shares a listening language. The test checks twenty translation branches, twenty-five receiver routes, per-microphone CPU model results and the performance report. Recognition, translation and synthesis use test doubles, so the results measure routing and processing only.
