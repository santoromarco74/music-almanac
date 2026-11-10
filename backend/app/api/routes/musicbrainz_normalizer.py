from __future__ import annotations
import re
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import get_db

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
TYPE_MAP = {"person":"PERSON","group":"GROUP","orchestra":"ORCHESTRA",
            "choir":"CHOIR","character":"CHARACTER","other":"OTHER"}

class NormalizeArtistRequest(BaseModel):
    existing_artist_id: UUID | None = None

def _year(value):
    return int(value[:4]) if isinstance(value,str) and re.match(r"^\\d{4}",value) else None

def _candidate(payload):
    name = payload.get("name")
    if not isinstance(name,str) or not name.strip():
        raise HTTPException(422,"Il payload MusicBrainz non contiene un nome valido.")
    span = payload.get("life-span") or {}
    country = payload.get("country")
    return {"canonical_name":name.strip(),"sort_name":payload.get("sort-name") or None,
            "artist_type":TYPE_MAP.get(str(payload.get("type") or "").strip().lower(),"OTHER"),
            "country_code":country.upper() if isinstance(country,str) and re.fullmatch(r"[A-Za-z]{2}",country) else None,
            "begin_year":_year(span.get("begin")),"end_year":_year(span.get("end")),
            "biography":None,"disambiguation":payload.get("disambiguation") or None}

def _raw(db,mbid,lock=False):
    suffix = " FOR UPDATE OF rr" if lock else ""
    row = db.execute(text(f"""
        SELECT rr.id,rr.payload,rr.processing_status,rr.ingestion_run_id
        FROM raw_records rr JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
        JOIN sources s ON s.id=ir.source_id
        WHERE rr.source_record_id=:mbid AND s.name='MusicBrainz' AND s.source_type='CATALOG'
        ORDER BY rr.received_at DESC LIMIT 1{suffix}
    """),{"mbid":mbid}).mappings().first()
    if row is None: raise HTTPException(404,"Record MusicBrainz non trovato in raw_records.")
    return row

def _aliases(payload):
    values=[]
    for item in payload.get("aliases") or []:
        if isinstance(item,dict) and isinstance(item.get("alias"),str) and item["alias"].strip():
            values.append({"alias":item["alias"].strip(),"sort_name":item.get("sort-name"),
                           "locale":item.get("locale"),"alias_type":item.get("type"),
                           "primary_for_locale":bool(item.get("primary"))})
    return values

def _tags(payload):
    return list(dict.fromkeys(x["name"].strip() for x in (payload.get("tags") or [])
                              if isinstance(x,dict) and isinstance(x.get("name"),str) and x["name"].strip()))

def _linked(db,mbid):
    return db.execute(text("""
        SELECT artist_id FROM external_identifiers
        WHERE namespace='MUSICBRAINZ_ARTIST' AND identifier=:mbid
    """),{"mbid":mbid}).scalar_one_or_none()

@router.get("/musicbrainz/artists/preview/{mbid}")
def preview(mbid: str, db: Session=Depends(get_db)):
    try: UUID(mbid)
    except ValueError as exc: raise HTTPException(422,"MBID non valido.") from exc
    raw=_raw(db,mbid)
    candidate=_candidate(raw["payload"])
    matches=db.execute(text("""
        SELECT id,canonical_name,artist_type FROM artists
        WHERE lower(canonical_name)=lower(:name) ORDER BY id
    """),{"name":candidate["canonical_name"]}).mappings().all()
    tags=_tags(raw["payload"])
    genres=db.execute(text("""
        SELECT id,name FROM genres WHERE lower(name)=ANY(:names) ORDER BY lower(name)
    """),{"names":[t.lower() for t in tags]}).mappings().all() if tags else []
    linked=_linked(db,mbid)
    return {"mbid":mbid,"raw_record_id":str(raw["id"]),
            "processing_status":raw["processing_status"],"normalized_candidate":candidate,
            "existing_artist_matches":[{"id":str(x["id"]),"canonical_name":x["canonical_name"],
                                        "artist_type":x["artist_type"]} for x in matches],
            "already_linked_artist_id":str(linked) if linked else None,
            "aliases":_aliases(raw["payload"]),"musicbrainz_tags":tags,
            "matched_local_genres":[{"id":str(x["id"]),"name":x["name"]} for x in genres],
            "notes":["area non viene convertita in country_code",
                     "gli alias sono memorizzati in artist_aliases",
                     "i tag vengono associati soltanto a generi locali già esistenti",
                     "il payload originale resta conservato in raw_records"]}

@router.post("/musicbrainz/artists/normalize/{mbid}")
def normalize(mbid: str, request: NormalizeArtistRequest, db: Session=Depends(get_db)):
    try: UUID(mbid)
    except ValueError as exc: raise HTTPException(422,"MBID non valido.") from exc
    db.rollback()
    try:
        with db.begin():
            raw=_raw(db,mbid,lock=True)
            candidate=_candidate(raw["payload"])
            linked=_linked(db,mbid)
            if linked:
                # Un MBID già associato non deve creare un nuovo artista, ma
                # il nuovo payload può contenere alias/tag aggiuntivi da integrare.
                artist_id = linked
                action = "ALREADY_LINKED"
            else:
                if request.existing_artist_id:
                    artist_id=request.existing_artist_id
                    exists=db.execute(text("SELECT id FROM artists WHERE id=:id"),
                                      {"id":artist_id}).scalar_one_or_none()
                    if not exists: raise HTTPException(404,"Artista canonico indicato non esistente.")
                    action="LINKED_TO_EXISTING"
                else:
                    matches=db.execute(text("""
                        SELECT id,canonical_name,artist_type FROM artists
                        WHERE lower(canonical_name)=lower(:name) ORDER BY id
                    """),{"name":candidate["canonical_name"]}).mappings().all()
                    if matches:
                        raise HTTPException(409,detail={"message":"Omonimia: selezionare esplicitamente l'artista canonico.",
                            "candidate_matches":[{"id":str(x["id"]),"canonical_name":x["canonical_name"],
                                                  "artist_type":x["artist_type"]} for x in matches]})
                    artist_id=db.execute(text("""
                        INSERT INTO artists (canonical_name,sort_name,artist_type,country_code,
                        begin_year,end_year,biography,disambiguation)
                        VALUES (:canonical_name,:sort_name,:artist_type,:country_code,
                        :begin_year,:end_year,:biography,:disambiguation) RETURNING id
                    """),candidate).scalar_one()
                    action="CREATED"

                db.execute(text("""
                    INSERT INTO external_identifiers(namespace,identifier,artist_id)
                    VALUES ('MUSICBRAINZ_ARTIST',:mbid,:artist_id)
                """),{"mbid":mbid,"artist_id":artist_id})

            source_id=db.execute(text("SELECT source_id FROM ingestion_runs WHERE id=:id"),
                                 {"id":raw["ingestion_run_id"]}).scalar_one_or_none()
            for alias in _aliases(raw["payload"]):
                db.execute(text("""
                    INSERT INTO artist_aliases
                    (artist_id,alias,sort_name,locale,alias_type,primary_for_locale,source_id)
                    VALUES (:artist_id,:alias,:sort_name,:locale,:alias_type,:primary_for_locale,:source_id)
                    ON CONFLICT DO NOTHING
                """),{"artist_id":artist_id,"source_id":source_id,**alias})

            for tag in _tags(raw["payload"]):
                genre_id=db.execute(text("""
                    SELECT id FROM genres WHERE lower(name)=lower(:name) ORDER BY id LIMIT 1
                """),{"name":tag}).scalar_one_or_none()
                if genre_id:
                    db.execute(text("""
                        INSERT INTO artist_genres(artist_id,genre_id)
                        VALUES (:artist_id,:genre_id) ON CONFLICT DO NOTHING
                    """),{"artist_id":artist_id,"genre_id":genre_id})

            db.execute(text("""
                UPDATE raw_records SET processing_status='PROCESSED',processed_at=now()
                WHERE id=:id
            """),{"id":raw["id"]})
        return {"status":action,"mbid":mbid,"artist_id":str(artist_id),
                "canonical_name":candidate["canonical_name"],
                "aliases_imported":len(_aliases(raw["payload"])),
                "tags_processed":len(_tags(raw["payload"])),
                "message":"Normalizzazione completata; payload originale conservato."}
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409,"Conflitto di integrità; ripetere la preview e verificare l'associazione MBID.") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(500,"Errore durante la normalizzazione dell'artista.") from exc
