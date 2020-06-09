from PySide2 import QtMultimedia, QtCore
from tinytag import TinyTag
from PySide2.QtCore import Signal
import sqlite3
import pathlib
import os
from PySide2.QtMultimedia import QMediaContent , QMediaPlaylist

file_path = pathlib.Path(__file__).parent.absolute();
class AudioMetadata():
    def __init__(self,file_path):
        tag = TinyTag.get(file_path);
        self.album = tag.album
        self.artist = tag.artist
        self.title = tag.title
        #may need to change
        self.path = file_path
        self.genre = tag.genre
        self.duration = tag.duration
        #Used when the meta data is represented in a database
        self.dbase_id = -1;

def setup_database():
    exists = os.path.isfile(str(file_path / 'lib.db')) 
    con = sqlite3.connect('lib.db')
    cur = con.cursor()
    if exists:
        print("already exists!!");
        return (con,cur) 
    cur.execute('''CREATE TABLE  songs (
                song_id INTEGER PRIMARY KEY,
                path      TEXT NOT NULL UNIQUE,
                title     TEXT NOT NULL,
                genre_id  INTEGER NOT NULL,
                artist_id INTEGER NOT NULL,
                album_id  INTEGER NOT NULL,
                duration INTEGER NOT NULL
                );''')
    cur.execute('''
                CREATE UNIQUE INDEX idx_songs_path
                ON songs (path);
                ''')
    cur.execute('''CREATE TABLE  playlists(
                playlist_id INTEGER PRIMARY KEY,
                name    TEXT NOT NULL UNIQUE
                    );
                ''')
    cur.execute('''
                CREATE UNIQUE INDEX idx_playlist_name
                ON playlists (name);
                ''')
    cur.execute('''
                CREATE TABLE playlist_group(
                playlist_id INTEGER NOT NULL,
                song_id INTEGER NOT NULL,
                PRIMARY KEY (playlist_id,song_id),
                FOREIGN KEY (playlist_id)
                    REFERENCES playlists (playlist_id)
                        ON DELETE NO ACTION
                        ON UPDATE NO ACTION,
                FOREIGN KEY (song_id)
                    REFERENCES songs (song_id)
                        ON DELETE NO ACTION
                        ON UPDATE NO ACTION
                );
                ''')
    con.commit()
    return (con,cur)
class Model(QtCore.QObject):

    playlistAdded = QtCore.Signal(str);
    #This will be Dumb But okay
    playlistUpdated = QtCore.Signal(str);
    def __init__(self):
        super().__init__(); 
    def init(self):
        self.database_con , self.database_cur = setup_database();
        
        self._genres = set()
        self._artists = set()
        self._albums = set()
        
        self._repeating = False
        self._shuffled = False
        
        self._playlists_mdata = {} # mdata = meta data
        self._playlists = {}
        self._current_playlist = None;
        self._current_playlist_mdata = None;
        self._current_playlist_name = None;
       
        self.player = QtMultimedia.QMediaPlayer(self)
        self.player.setVolume(50);
    def shut_down(self):
        self.database_con.close();
    def read_from_database(self):
        t_cursor = self.database_con.execute('''SELECT playlist_id, name FROM playlists;''')
        tmp_ls = []
        for row in t_cursor:
            tmp_ls.append((row[0],row[1]));
        for row in tmp_ls:
            t_cursor2 = self.database_con.execute('''SELECT playlist_id,path,songs.song_id
                                     FROM playlist_group
                                     INNER JOIN songs
                                     on songs.song_id = playlist_group.song_id
                                     where playlist_id = ?;''',
                                                  (row[0],))
            self.add_playlist(row[1])
            for nrow in t_cursor2:
                print("Herello" , nrow[1],row[1])
                self.add_file(nrow[1],row[1]);

            
    def update_playback_mode(self):
        if self._current_playlist == None : return 
        if self._repeating:
            self._current_playlist.setPlaybackMode(QMediaPlaylist.CurrentItemInLoop);
        elif self._shuffled:
            self._current_playlist.setPlaybackMode(QMediaPlaylist.Random)
        else:
            self._current_playlist.setPlaybackMode(QMediaPlaylist.Loop);

    def set_current_playlist(self,playlist_name):
        self._current_playlist_name = playlist_name
        self._current_playlist = self._playlists[playlist_name];
        self._current_playlist_mdata = self._playlists_mdata[playlist_name];
        self.update_playback_mode();
        self.player.setPlaylist(self._current_playlist);
        
    def set_repeat(self,flag):
        self._repeating = flag
        self.update_playback_mode()
    
    def set_shuffled(self,flag):
        self._shuffled = flag;
        self.update_playback_mode()

    def add_playlist(self,name):
        if name in self._playlists :
            print("can't add that playlist")
            return False
        self._playlists_mdata[name] = [];
        new_playlist = QtMultimedia.QMediaPlaylist()
        self._playlists[name] = new_playlist;
        new_playlist.dbase_id = self.add_playlist_to_database(name);
        self.playlistAdded.emit(name);

    def seek(self,p_percent): #position is normalised from 0 to 1
        self.player.setPosition(p_percent * self.player.duration());

    def add_file(self,path,playlist_name):
        n_media = QtMultimedia.QMediaContent(QtCore.QUrl.fromLocalFile(path));
        cur_playlist = self._playlists[playlist_name]
        cur_playlist.addMedia(n_media)
        mdata = AudioMetadata(path)
        mdata.dbase_id = self.add_song_to_database(mdata);
        #if playlist_name != "Play Now":
        self.add_song_to_database_playlist(mdata,cur_playlist);
        self._playlists_mdata[playlist_name].append(mdata);
        self.playlistUpdated.emit(playlist_name);
        return self._playlists[playlist_name].mediaCount() - 1;

    def add_playlist_to_database(self,name):
        self.database_cur.execute('''
                                 INSERT OR IGNORE INTO playlists values
                                 (NULL,?);
                                    ''',(name,))
        self.database_con.commit();
        return self.database_cur.execute('''
                                      SELECT playlist_id FROM playlists
                                      WHERE name = ?;
                                      ''',(name,)).fetchone()[0];
    def add_song_to_database_playlist(self,mdata,playlist):
        self.database_cur.execute('''INSERT OR IGNORE INTO playlist_group values
                                  (?,?);''',(playlist.dbase_id,mdata.dbase_id))
        self.database_con.commit()
    def add_song_to_database(self,mdata):
        data_tuple =  (mdata.path,mdata.title,
                       mdata.genre,mdata.artist,mdata.album
                       ,mdata.duration)
        self.database_cur.execute('''INSERT OR IGNORE INTO songs values 
                                  (NULL,?,?,?,?,?,? );''',data_tuple)   
        self.database_con.commit()
        return self.database_cur.execute('''
                                      SELECT song_id FROM songs
                                      WHERE path = ?;
                                      ''',(mdata.path,)).fetchone()[0];
    def open_file(self,index,playlist_name):
        if playlist_name != self._current_playlist_name:
            self.set_current_playlist(playlist_name);
        self._current_playlist.setCurrentIndex(index);
        self.player.play()
    
    def get_playlist_mdata(self,name):
        return self._playlists_mdata[name];
    def get_current_media_data(self):
        return self._current_playlist_mdata[self._current_playlist.currentIndex()];
    def get_media_data(self,index,playlist_name):
        return  self._playlists_mdata[playlist_name][index]
    def set_volume(self,vol):
        self.player.setVolume(vol);
    def pause(self):
        self.player.pause()
    def play(self):
        self.player.play()
    def stop(self):
        self.player.stop()
    def forwards(self):
        self._current_playlist.next()
    def rewind(self):
        self._current_playlist.previous()
    def get_position(self):
        if (self.player.duration() == 0) : return None;
        return self.player.position() / self.player.duration();

main_model = Model();
