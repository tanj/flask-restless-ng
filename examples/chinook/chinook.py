from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from flask_restless import APIManager

Base = declarative_base()


class Artist(Base):
    __tablename__ = 'artists'

    id = Column('ArtistId', Integer, primary_key=True)
    name = Column('name', String)


class Album(Base):
    __tablename__ = 'albums'

    id = Column('AlbumId', Integer, primary_key=True)
    title = Column('Title', String)
    artist_id = Column('ArtistId', Integer, ForeignKey('artists.ArtistId'))

    artist = relationship('Artist')


class Track(Base):
    __tablename__ = 'tracks'

    id = Column('TrackId', Integer, primary_key=True)
    name = Column('Name', String(200))
    composer = Column('Composer', String(220))
    album_id = Column('AlbumId', Integer, ForeignKey('albums.AlbumId'))

    album = relationship('Album')


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chinook.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = True

db = SQLAlchemy()
db.init_app(app)


api_manager = APIManager(app=app, session=db.session)
api_manager.create_api(Album, collection_name="albums")
api_manager.create_api(Artist, collection_name="artists")
api_manager.create_api(Track, collection_name="tracks")


if __name__ == '__main__':
    app.run(debug=True)
