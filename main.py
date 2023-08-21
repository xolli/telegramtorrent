#!/usr/bin/env python3
import libtorrent as lt
from shutil import make_archive, rmtree
import asyncio
import time
import os

# Import the client
from telethon import TelegramClient, events
from telethon.tl import types

# Enable logging
import logging

# This is a helper method to access environment variables or
# prompt the user to type them in the terminal if missing.
from telethon.tl.types import PeerUser

# Define some variables so the code reads easier
session = "firstsession"
api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
download_path = "./"
debug_enabled = ('DEBUG_ENABLED' in os.environ)

allowed_users = [] # ids of allowed users (int)

if (debug_enabled):
    logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.DEBUG)
else:
    logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s', level=logging.ERROR)

number_of_parallel_downloads = int(os.environ.get('TG_MAX_PARALLEL', 10))
maximum_seconds_per_download = int(os.environ.get('TG_DL_TIMEOUT', 3600))

ses = lt.session({'listen_interfaces': '0.0.0.0:6881'})

# Create a queue that we will use to store our downloads.
queue = asyncio.Queue()

# Create tmp path to store downloads until completed
tmp_path = os.path.join(download_path, "tmp")
os.makedirs(tmp_path, exist_ok=True)


def split(filename, block_size):
    input_file = open(filename, "rb")
    size_buffer = 100 * 1024 * 1024
    size_file = os.path.getsize("./" + filename)
    count_output_files = size_file // block_size
    if size_file % block_size != 0:
        count_output_files += 1
    count_zero = len(str(count_output_files - 1))
    split_files = []
    for i in range(count_output_files):
        prev_zero_count = count_zero - len(str(i))
        output_file = open(filename + "_" + prev_zero_count * "0" + str(i), "wb")
        split_files.append(filename + "_" + prev_zero_count * "0" + str(i))
        count_bytes = 0
        while count_bytes != block_size:
            buffer = input_file.read(min(size_buffer, block_size - count_bytes))
            if (len(buffer) == 0):
                break
            count_bytes += output_file.write(buffer)
        output_file.close()
    input_file.close()
    return split_files


def pack_dir(archivename, dirname):
    make_archive(archivename, 'zip', dirname)


async def download_torrent(message, torrent_filename):
    info = lt.torrent_info(torrent_filename)
    h = ses.add_torrent({'ti': info, 'save_path': './' + str(message.id)})
    s = h.status()
    await message.edit("starting " + s.name)
    prev_progress = None
    while (not s.is_seeding):
        s = h.status()
        if (prev_progress is None or s.progress - prev_progress > 1e-3):
            await message.edit('\r%.2f%% complete (down: %.1f kB/s up: %.1f kB/s peers: %d) %s' % (
                s.progress * 100, s.download_rate / 1000, s.upload_rate / 1000,
                s.num_peers, s.state))
            prev_progress = s.progress
        alerts = ses.pop_alerts()
        for a in alerts:
            if a.category() & lt.alert.category_t.error_notification:
                print(a)
        await asyncio.sleep(1)
    await message.edit(h.status().name + ' complete')


async def download_torrent_file(update, message):
    file_path = tmp_path
    file_name = 'unknown name'
    attributes = update.message.media.document.attributes
    for attr in attributes:
        if isinstance(attr, types.DocumentAttributeFilename):
            file_name = attr.file_name
            file_path = os.path.join(file_path, attr.file_name)
    if (file_name.split(".")[-1] != "torrent"):
        raise Exception('File is not torrent. Cancel Downloading')
    await message.edit('Downloading torrent-file...')
    print("[%s] Download started at %s" % (file_name, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
    loop = asyncio.get_event_loop()
    task = loop.create_task(client.download_media(update.message, file_path))
    download_result = await asyncio.wait_for(task, timeout=maximum_seconds_per_download)
    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    _, filename = os.path.split(download_result)
    final_path = os.path.join(download_path, filename)
    os.rename(download_result, final_path)
    print("[%s] Successfully downloaded to %s at %s" % (file_name, final_path, end_time))
    return file_name, final_path


async def worker(worker_name):
    while True:
        # Get a "work item" out of the queue.
        queue_item = await queue.get()
        update = queue_item[0]
        message = queue_item[1]
        id_str = str(message.id)
        try:
            file_name, final_path = await download_torrent_file(update, message)
            if (len(file_name.split(".")) >= 2):
                name = ".".join(file_name.split(".")[:-1])
            else:
                name = id_str
            await message.edit('Torrent-file downloaded')
            await download_torrent(message, final_path)
            os.remove(final_path)
            await message.edit('start create zip archive')
            pack_dir(name, './' + id_str)
            rmtree('./' + id_str, ignore_errors=True)
            size_file = os.path.getsize('./' + name + '.zip')
            upload_files = []
            size_limit = 1500 * 1024 * 1024
            if size_file > size_limit:
                await message.edit('start split files')
                upload_files = split(name + '.zip', size_limit)
                os.remove(name + '.zip')
            else:
                upload_files.append(name + '.zip')
            for file in upload_files:
                await message.edit('Sending file "' + file + '"...')
                await client.send_file('uxolli', './' + file)
                os.remove(file)
            await message.edit('End')
        except asyncio.TimeoutError:
            print("[%s] Timeout reached at %s" % (file_name, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
            await message.edit('Error!')
            await update.reply('ERROR: Timeout reached downloading this file')
        except Exception as e:
            print("[EXCEPTION]: %s" % (str(e)))
            print("[%s] Exception at %s" % (file_name, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
            await message.edit('Error!')
            await update.reply('ERROR: Exception %s raised downloading this file: %s' % (e.__class__.__name__, str(e)))
        # Notify the queue that the "work item" has been processed.
        queue.task_done()


client = TelegramClient(session, api_id, api_hash, request_retries=10, flood_sleep_threshold=120)

def user_is_allowed(peer_id):
    for user in allowed_users:
        if peer_id == PeerUser(user_id=user):
            return True
    return False

# This is our update handler. It is called when a new update arrives.
# Register `events.NewMessage` before defining the client.
@events.register(events.NewMessage)
async def handler(update):
    if (debug_enabled):
        print(update)
    if user_is_allowed(update.message.peer_id) and update.message.media is not None:
        file_name = 'unknown name'
        attributes = update.message.media.document.attributes
        for attr in attributes:
            if isinstance(attr, types.DocumentAttributeFilename):
                file_name = attr.file_name
        print("[%s] Download queued at %s" % (file_name, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
        message = await update.reply('In queue')
        await queue.put([update, message])
    elif user_is_allowed(update.message.peer_id):
        await update.reply('Send me .torrent file!')


try:
    # Create worker tasks to process the queue concurrently.
    tasks = []
    for i in range(number_of_parallel_downloads):
        loop = asyncio.get_event_loop()
        task = loop.create_task(worker(f'worker-{i}'))
        tasks.append(task)

    # Start client with TG_BOT_TOKEN string
    client.start()
    # Register the update handler so that it gets called
    client.add_event_handler(handler)

    # Run the client until Ctrl+C is pressed, or the client disconnects
    print('Successfully started (Press Ctrl+C to stop)')
    client.run_until_disconnected()
finally:
    # Cancel our worker tasks.
    for task in tasks:
        task.cancel()
    # Wait until all worker tasks are cancelled.
    # await asyncio.gather(*tasks, return_exceptions=True)
    # Stop Telethon client
    client.disconnect()
    print('Stopped!')
