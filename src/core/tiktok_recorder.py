import os
import time
from http.client import HTTPException
from threading import Thread

from requests import RequestException

from core.tiktok_api import TikTokAPI
from utils.logger_manager import logger
from utils.video_management import VideoManagement
from upload.telegram import Telegram
from utils.custom_exceptions import LiveNotFound, UserLiveError, TikTokRecorderError
from utils.enums import Mode, Error, TimeOut, TikTokError


class TikTokRecorder:
    def __init__(
        self,
        url,
        user,
        room_id,
        mode,
        automatic_interval,
        cookies,
        proxy,
        output,
        duration,
        use_telegram,
    ):
        # Setup TikTok API client
        self.tiktok = TikTokAPI(proxy=proxy, cookies=cookies)

        # TikTok Data
        self.url = url
        self.user = user
        self.room_id = room_id

        # Tool Settings
        self.mode = mode
        self.automatic_interval = automatic_interval
        self.duration = duration
        self.output = output

        # Upload Settings
        self.use_telegram = use_telegram

        # Check if the user's country is blacklisted
        self.check_country_blacklisted()

        # Retrieve sec_uid if the mode is FOLLOWERS
        if self.mode == Mode.FOLLOWERS:
            self.sec_uid = self.tiktok.get_sec_uid()
            if self.sec_uid is None:
                raise TikTokRecorderError("Failed to retrieve sec_uid.")

            logger.info("Followers mode activated\n")
        else:
            # Get live information based on the provided user data
            if self.url:
                self.user, self.room_id = self.tiktok.get_room_and_user_from_url(
                    self.url
                )

            if not self.user:
                self.user = self.tiktok.get_user_from_room_id(self.room_id)

            if not self.room_id:
                self.room_id = self.tiktok.get_room_id_from_user(self.user)

            logger.info(f"USERNAME: {self.user}" + ("\n" if not self.room_id else ""))
            if self.room_id:
                logger.info(
                    f"ROOM_ID:  {self.room_id}"
                    + ("\n" if not self.tiktok.is_room_alive(self.room_id) else "")
                )

        # If proxy is provided, set up the HTTP client without the proxy
        if proxy:
            self.tiktok = TikTokAPI(proxy=None, cookies=cookies)

    def run(self):
        """
        runs the program in the selected mode.

        If the mode is MANUAL, it checks if the user is currently live and
        if so, starts recording.

        If the mode is AUTOMATIC, it continuously checks if the user is live
        and if not, waits for the specified timeout before rechecking.
        If the user is live, it starts recording.

        if the mode is FOLLOWERS, it continuously checks the followers of
        the authenticated user. If any follower is live, it starts recording
        their live stream in a separate process.
        """
        if self.mode == Mode.MANUAL:
            self.manual_mode()

        elif self.mode == Mode.AUTOMATIC:
            self.automatic_mode()

        elif self.mode == Mode.FOLLOWERS:
            self.followers_mode()

    def manual_mode(self):
        if not self.tiktok.is_room_alive(self.room_id):
            raise UserLiveError(f"@{self.user}: {TikTokError.USER_NOT_CURRENTLY_LIVE}")

        self.start_recording(self.user, self.room_id)

    def automatic_mode(self):
        while True:
            try:
                self.room_id = self.tiktok.get_room_id_from_user(self.user)
                self.manual_mode()

            except UserLiveError as ex:
                logger.info(ex)
                logger.info(
                    f"Waiting {self.automatic_interval} minutes before recheck\n"
                )
                time.sleep(self.automatic_interval * TimeOut.ONE_MINUTE)

            except LiveNotFound as ex:
                logger.error(f"Live not found: {ex}")
                logger.info(
                    f"Waiting {self.automatic_interval} minutes before recheck\n"
                )
                time.sleep(self.automatic_interval * TimeOut.ONE_MINUTE)

            except ConnectionError:
                logger.error(Error.CONNECTION_CLOSED_AUTOMATIC)
                time.sleep(TimeOut.CONNECTION_CLOSED * TimeOut.ONE_MINUTE)

            except Exception as ex:
                logger.error(f"Unexpected error: {ex}\n")

    def followers_mode(self):
        active_recordings = {}  # follower -> Process

        while True:
            try:
                followers = self.tiktok.get_followers_list(self.sec_uid)

                for follower in followers:
                    if follower in active_recordings:
                        if not active_recordings[follower].is_alive():
                            logger.info(f"Recording of @{follower} finished.")
                            del active_recordings[follower]
                        else:
                            continue

                    try:
                        room_id = self.tiktok.get_room_id_from_user(follower)

                        if not room_id or not self.tiktok.is_room_alive(room_id):
                            # logger.info(f"@{follower} is not live. Skipping...")
                            continue

                        logger.info(f"@{follower} is live. Starting recording...")

                        thread = Thread(
                            target=self.start_recording,
                            args=(follower, room_id),
                            daemon=True,
                        )
                        thread.start()
                        active_recordings[follower] = thread

                        time.sleep(2.5)

                    except Exception as e:
                        logger.error(f"Error while processing @{follower}: {e}")
                        continue

                print()
                delay = self.automatic_interval * TimeOut.ONE_MINUTE
                logger.info(f"Waiting {delay} minutes for the next check...")
                time.sleep(delay)

            except UserLiveError as ex:
                logger.info(ex)
                logger.info(
                    f"Waiting {self.automatic_interval} minutes before recheck\n"
                )
                time.sleep(self.automatic_interval * TimeOut.ONE_MINUTE)

            except ConnectionError:
                logger.error(Error.CONNECTION_CLOSED_AUTOMATIC)
                time.sleep(TimeOut.CONNECTION_CLOSED * TimeOut.ONE_MINUTE)

            except Exception as ex:
                logger.error(f"Unexpected error: {ex}\n")

    def start_recording(self, user, room_id):
        """
        Start recording live
        """
        live_url = self.tiktok.get_live_url(room_id)
        if not live_url:
            raise LiveNotFound(TikTokError.RETRIEVE_LIVE_URL)

        # Prepare output directory (Req 1: UserID folder)
        if isinstance(self.output, str) and self.output != "":
             # Ensure path separators are correct
            if not self.output.endswith(os.sep):
                self.output += os.sep
            
            # Create user specific folder: output/UserID/
            self.output = os.path.join(self.output, user)
            os.makedirs(self.output, exist_ok=True)
            if not self.output.endswith(os.sep):
                self.output += os.sep

        # Helper to generate filename
        def get_output_path():
            current_date = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
            return f"{self.output}{user}_{current_date}_flv.mp4"

        output = get_output_path()

        if self.duration:
            logger.info(f"Started recording for {self.duration} seconds ")
        else:
            logger.info("Started recording...")

        buffer_size = 512 * 1024  # 512 KB buffer
        buffer = bytearray()

        if self.use_telegram:
            Telegram().send_message(
                f"🔴 <b>Recording Started</b>\n"
                f"👤 User: <code>{user}</code>\n"
                f"📅 Date: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
            )

        import msvcrt # Windows only

        logger.info("[PRESS CTRL + C OR 'Q' TO STOP RECORDING USER]")
        
        # Non-blocking keyboard check wrapper
        def check_keypress():
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key.lower() == b'q':
                    return True
            return False

        # Segment setup (Req 2: 30 mins)
        segment_duration = 30 * 60  
        segment_start_time = time.time()
        
        stop_recording = False

        while not stop_recording:
            with open(output, "wb") as out_file:
                logger.info(f"Recording to file: {output}")
                try:
                    if not self.tiktok.is_room_alive(room_id):
                        logger.info("User is no longer live. Stopping recording.")
                        stop_recording = True
                        break

                    start_time = time.time()
                    for chunk in self.tiktok.download_live_stream(live_url):
                        buffer.extend(chunk)
                        if len(buffer) >= buffer_size:
                            out_file.write(buffer)
                            buffer.clear()
                        
                        # Check for 'q' key press
                        if check_keypress():
                            logger.info("Stop signal received (Q pressed). Stopping recording...")
                            stop_recording = True
                            break

                        # Check global duration
                        elapsed_time = time.time() - start_time
                        if self.duration and elapsed_time >= self.duration:
                            stop_recording = True
                            break
                        
                        # Check segment duration (30 mins)
                        segment_elapsed = time.time() - segment_start_time
                        if segment_elapsed >= segment_duration:
                            logger.info(f"Segment limit reached ({segment_duration}s). Switching file.")
                            # Flush and close current file
                            if buffer:
                                out_file.write(buffer)
                                buffer.clear()
                            out_file.flush()
                            out_file.close()

                            # Convert finished segment in background
                            Thread(target=VideoManagement.convert_flv_to_mp4, args=(output,)).start()

                            # Notify Telegram about segment finish (optional, but good for tracking)
                            if self.use_telegram:
                                Telegram().send_message(f"📁 <b>Segment Saved</b>\nFile: <code>{os.path.basename(output).replace('_flv.mp4', '.mp4')}</code>")

                            # Start new segment
                            output = get_output_path()
                            segment_start_time = time.time()
                            
                            # Re-open new file (break inner loop to re-enter with block)
                            break 

                except ConnectionError:
                    if self.mode == Mode.AUTOMATIC:
                        logger.error(Error.CONNECTION_CLOSED_AUTOMATIC)
                        time.sleep(TimeOut.CONNECTION_CLOSED * TimeOut.ONE_MINUTE)

                except (RequestException, HTTPException):
                    time.sleep(2)

                except KeyboardInterrupt:
                    logger.info("Recording stopped by user.")
                    stop_recording = True

                except Exception as ex:
                    logger.error(f"Unexpected error: {ex}\n")
                    stop_recording = True

                finally:
                    if buffer:
                        # If file is closed in loop (segment switch), this might fail?
                        # No, out_file is context manager scoped, but we close it manually.
                        # Actually 'with' handles close. If we break, 'with' exit closes it.
                        if not out_file.closed:
                            out_file.write(buffer)
                            buffer.clear()
                            out_file.flush()

        # Final cleanup for last file
        logger.info(f"Recording finished: {output}\n")
        VideoManagement.convert_flv_to_mp4(output)

        if self.use_telegram:
            end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            Telegram().send_message(
                f"✅ <b>Recording Finished</b>\n"
                f"👤 User: <code>{user}</code>\n"
                f"🏁 End Time: {end_time}\n"
                f"📁 Last File: <code>{os.path.basename(output.replace('_flv.mp4', '.mp4'))}</code>"
            )

    def check_country_blacklisted(self):
        is_blacklisted = self.tiktok.is_country_blacklisted()
        if not is_blacklisted:
            return False

        if self.room_id is None:
            raise TikTokRecorderError(TikTokError.COUNTRY_BLACKLISTED)

        if self.mode == Mode.AUTOMATIC:
            raise TikTokRecorderError(TikTokError.COUNTRY_BLACKLISTED_AUTO_MODE)

        elif self.mode == Mode.FOLLOWERS:
            raise TikTokRecorderError(TikTokError.COUNTRY_BLACKLISTED_FOLLOWERS_MODE)

        return is_blacklisted
