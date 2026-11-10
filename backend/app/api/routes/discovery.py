import csv, io, json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import get_db

router=APIRouter(tags=["discovery"])
EVENT_TYPES={"BIRTH","DEATH","RELEASE","CONCERT","FESTIVAL","RECORDING","BROADCAST","AWARD","CHART","INDUSTRY","OTHER"}

def rows(db,sql,p=None): return [dict(r) for r in db.execute(text(sql),p or {}).mappings().all()]

@router.get("/calendar")
def calendar(year:int|None=None,month:int|None=Query(None,ge=1,le=12),day:int|None=Query(None,ge=1,le=31),event_type:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),db:Session=Depends(get_db)):
    if event_type and event_type.upper() not in EVENT_TYPES: raise HTTPException(422,"event_type non valido.")
    if month is not None and year is None: raise HTTPException(422,"year è obbligatorio quando si specifica month.")
    if day is not None and month is None: raise HTTPException(422,"month è obbligatorio quando si specifica day.")
    return rows(db,"""SELECT e.*,v.name AS venue_name,v.city AS venue_city FROM events e LEFT JOIN venues v ON v.id=e.venue_id WHERE (CAST(:y AS SMALLINT) IS NULL OR e.event_year=:y) AND (CAST(:m AS SMALLINT) IS NULL OR e.event_month=:m) AND (CAST(:d AS SMALLINT) IS NULL OR e.event_day=:d) AND (CAST(:t AS TEXT) IS NULL OR e.event_type=CAST(:t AS event_type)) ORDER BY e.event_month NULLS LAST,e.event_day NULLS LAST,e.event_year,e.title OFFSET :o LIMIT :n""",{"y":year,"m":month,"d":day,"t":event_type.upper() if event_type else None,"o":offset,"n":limit})

@router.get("/search")
def search(q:str=Query(...,min_length=2),kind:str="all",limit:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    if kind not in {"all","artists","releases","events"}: raise HTTPException(422,"kind deve essere all, artists, releases o events.")
    term=f"%{q.strip()}%"; out={}
    if kind in {"all","artists"}: out["artists"]=rows(db,"SELECT id,canonical_name AS title,artist_type,country_code FROM artists WHERE canonical_name ILIKE :q OR sort_name ILIKE :q ORDER BY canonical_name LIMIT :n",{"q":term,"n":limit})
    if kind in {"all","releases"}: out["releases"]=rows(db,"SELECT id,title,release_year,format FROM releases WHERE title ILIKE :q ORDER BY release_year DESC NULLS LAST,title LIMIT :n",{"q":term,"n":limit})
    if kind in {"all","events"}: out["events"]=rows(db,"SELECT id,title,event_type,event_year,event_month,event_day FROM events WHERE title ILIKE :q ORDER BY event_year DESC NULLS LAST,title LIMIT :n",{"q":term,"n":limit})
    return {"query":q,"results":out}

@router.get("/export/{entity}")
def export_data(entity:str,format:str="json",limit:int=Query(5000,ge=1,le=20000),db:Session=Depends(get_db)):
    queries={"artists":"SELECT * FROM artists ORDER BY canonical_name LIMIT :n","genres":"SELECT * FROM genres ORDER BY name LIMIT :n","releases":"SELECT * FROM releases ORDER BY release_year DESC NULLS LAST,title LIMIT :n","events":"SELECT * FROM events ORDER BY event_year DESC NULLS LAST,title LIMIT :n","awards":"SELECT * FROM awards ORDER BY edition_year DESC NULLS LAST,name LIMIT :n","editorial-items":"SELECT * FROM editorial_items ORDER BY created_at DESC LIMIT :n"}
    if entity not in queries: raise HTTPException(404,"Entità esportabile non supportata.")
    if format not in {"json","csv"}: raise HTTPException(422,"format deve essere json o csv.")
    data=rows(db,queries[entity],{"n":limit})
    if format=="json":
        def default(v): return v.isoformat() if hasattr(v,"isoformat") else str(v)
        content=json.dumps(data,ensure_ascii=False,default=default,indent=2)
        return StreamingResponse(iter([content]),media_type="application/json",headers={"Content-Disposition":f'attachment; filename="music-almanac-{entity}.json"'})
    stream=io.StringIO(); fields=list(data[0].keys()) if data else []
    writer=csv.DictWriter(stream,fieldnames=fields,extrasaction="ignore");
    if fields: writer.writeheader(); writer.writerows(data)
    return StreamingResponse(iter([stream.getvalue()]),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="music-almanac-{entity}.csv"'})
