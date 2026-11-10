from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import get_db

router=APIRouter(tags=["events"])
TYPES={"BIRTH","DEATH","RELEASE","CONCERT","FESTIVAL","RECORDING","BROADCAST","AWARD","CHART","INDUSTRY","OTHER"}
STATUSES={"VERIFIED","CONFIRMED","PRELIMINARY","TO_VERIFY","UNCERTAIN"}

def one(db,sql,p=None):
    x=db.execute(text(sql),p or {}).mappings().first()
    return dict(x) if x else None

def event_detail(db,eid):
    x=one(db,"SELECT e.*,v.name venue_name,v.city venue_city FROM events e LEFT JOIN venues v ON v.id=e.venue_id WHERE e.id=:id",{"id":eid})
    if not x:raise HTTPException(404,"Evento non trovato.")
    x["artists"]=[dict(a) for a in db.execute(text("SELECT a.id,a.canonical_name,ea.role FROM event_artists ea JOIN artists a ON a.id=ea.artist_id WHERE ea.event_id=:id ORDER BY a.canonical_name"),{"id":eid}).mappings().all()]
    return x

@router.get("/venues")
def venues(q:str|None=None,city:str|None=None,country_code:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    xs=db.execute(text("SELECT * FROM venues WHERE (CAST(:q AS TEXT) IS NULL OR name ILIKE '%'||:q||'%') AND (CAST(:city AS TEXT) IS NULL OR city ILIKE '%'||:city||'%') AND (CAST(:c AS CHAR(2)) IS NULL OR country_code=:c) ORDER BY lower(name),city,id OFFSET :o LIMIT :n"),{"q":q,"city":city,"c":country_code.upper() if country_code else None,"o":offset,"n":limit}).mappings().all()
    return [dict(x) for x in xs]

@router.post("/venues",status_code=201)
def create_venue(p:dict,db:Session=Depends(get_db)):
    name=str(p.get("name","")).strip()
    if not name:raise HTTPException(422,"name obbligatorio.")
    x=one(db,"INSERT INTO venues(name,city,region,country_code,latitude,longitude) VALUES (:name,:city,:region,:country,:lat,:lon) RETURNING *",{"name":name,"city":p.get("city"),"region":p.get("region"),"country":(p.get("country_code") or "").upper() or None,"lat":p.get("latitude"),"lon":p.get("longitude")});db.commit();return x

@router.get("/venues/{rid}")
def get_venue(rid:UUID,db:Session=Depends(get_db)):
    x=one(db,"SELECT * FROM venues WHERE id=:id",{"id":rid})
    if not x:raise HTTPException(404,"Venue non trovato.")
    return x

@router.patch("/venues/{rid}")
def patch_venue(rid:UUID,p:dict,db:Session=Depends(get_db)):
    old=get_venue(rid,db);allowed={"name","city","region","country_code","latitude","longitude"};d={k:v for k,v in p.items() if k in allowed}
    if not d:return old
    if "name" in d:
        if not str(d["name"]).strip():raise HTTPException(422,"name non valido.")
        d["name"]=str(d["name"]).strip()
    if d.get("country_code"):d["country_code"]=d["country_code"].upper()
    x=one(db,"UPDATE venues SET "+",".join(f"{k}=:{k}" for k in d)+" WHERE id=:id RETURNING *",{**d,"id":rid});db.commit();return x

@router.delete("/venues/{rid}",status_code=204)
def delete_venue(rid:UUID,db:Session=Depends(get_db)):
    x=db.execute(text("DELETE FROM venues WHERE id=:id"),{"id":rid})
    if not x.rowcount:db.rollback();raise HTTPException(404,"Venue non trovato.")
    db.commit();return Response(status_code=204)

@router.get("/events")
def events(q:str|None=None,event_type:str|None=None,year:int|None=None,month:int|None=Query(None,ge=1,le=12),day:int|None=Query(None,ge=1,le=31),artist_id:UUID|None=None,status:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    xs=db.execute(text("""SELECT e.id,e.title,e.event_type,e.event_year,e.event_month,e.event_day,e.date_precision,e.event_date,e.end_date,e.country_code,e.status,v.name venue_name,v.city venue_city
      FROM events e LEFT JOIN venues v ON v.id=e.venue_id WHERE (CAST(:q AS TEXT) IS NULL OR e.title ILIKE '%'||:q||'%')
      AND (CAST(:t AS TEXT) IS NULL OR e.event_type=CAST(:t AS event_type)) AND (CAST(:y AS SMALLINT) IS NULL OR e.event_year=:y)
      AND (CAST(:m AS SMALLINT) IS NULL OR e.event_month=:m) AND (CAST(:d AS SMALLINT) IS NULL OR e.event_day=:d)
      AND (CAST(:a AS UUID) IS NULL OR EXISTS(SELECT 1 FROM event_artists x WHERE x.event_id=e.id AND x.artist_id=:a))
      AND (CAST(:s AS TEXT) IS NULL OR e.status=CAST(:s AS verification_status))
      ORDER BY e.event_year,e.event_month NULLS FIRST,e.event_day NULLS FIRST,lower(e.title) OFFSET :o LIMIT :n"""),
      {"q":q,"t":event_type.upper() if event_type else None,"y":year,"m":month,"d":day,"a":artist_id,"s":status.upper() if status else None,"o":offset,"n":limit}).mappings().all()
    return [dict(x) for x in xs]

@router.post("/events",status_code=201)
def create_event(p:dict,db:Session=Depends(get_db)):
    title=str(p.get("title","")).strip();kind=str(p.get("event_type","")).upper();precision=str(p.get("date_precision","YEAR")).upper()
    y=p.get("event_year");m=p.get("event_month");d=p.get("event_day")
    if not title or kind not in TYPES or p.get("status","TO_VERIFY") not in STATUSES:raise HTTPException(422,"Titolo, tipo o stato evento non valido.")
    if precision not in {"YEAR","MONTH","DAY"} or y is None:raise HTTPException(422,"Precisione o anno evento non validi.")
    if precision=="YEAR" and (m is not None or d is not None):raise HTTPException(422,"YEAR richiede mese e giorno nulli.")
    if precision=="MONTH" and (m is None or d is not None):raise HTTPException(422,"MONTH richiede mese e giorno nullo.")
    try:evdate=date(y,m,d) if precision=="DAY" else None
    except (TypeError,ValueError) as e:raise HTTPException(422,"Data evento non valida.") from e
    data={"title":title,"kind":kind,"description":p.get("description"),"year":y,"month":m,"day":d,"precision":precision,"date":evdate,"end":p.get("end_date"),"ann":p.get("announcement_date"),"venue":p.get("venue_id"),"country":(p.get("country_code") or "").upper() or None,"status":p.get("status","TO_VERIFY")}
    try:
        x=one(db,"""INSERT INTO events(title,event_type,description,event_year,event_month,event_day,date_precision,event_date,end_date,announcement_date,venue_id,country_code,status)
        VALUES (:title,CAST(:kind AS event_type),:description,:year,:month,:day,CAST(:precision AS date_precision),:date,:end,:ann,:venue,:country,CAST(:status AS verification_status)) RETURNING id""",data);eid=x["id"]
        for a in p.get("artists",[]):
            aid=a.get("artist_id")
            if not db.execute(text("SELECT id FROM artists WHERE id=:id"),{"id":aid}).scalar_one_or_none():raise HTTPException(422,"Artista associato non esistente.")
            db.execute(text("INSERT INTO event_artists(event_id,artist_id,role) VALUES (:e,:a,:r) ON CONFLICT DO NOTHING"),{"e":eid,"a":aid,"r":a.get("role","PARTICIPANT")})
        db.commit();return event_detail(db,eid)
    except IntegrityError as e:db.rollback();raise HTTPException(422,"Venue o riferimento evento non valido.") from e

@router.get("/events/{rid}")
def get_event(rid:UUID,db:Session=Depends(get_db)):return event_detail(db,rid)

@router.patch("/events/{rid}")
def patch_event(rid:UUID,p:dict,db:Session=Depends(get_db)):
    old=event_detail(db,rid);allowed={"title","event_type","description","event_year","event_month","event_day","date_precision","end_date","announcement_date","venue_id","country_code","status"};d={k:v for k,v in p.items() if k in allowed};artists=p.get("artists")
    merged={**old,**d};precision=str(merged.get("date_precision","YEAR")).upper();y=merged.get("event_year");m=merged.get("event_month");day=merged.get("event_day")
    if precision not in {"YEAR","MONTH","DAY"} or y is None:raise HTTPException(422,"Precisione o anno evento non validi.")
    if precision=="YEAR" and (m is not None or day is not None):raise HTTPException(422,"YEAR richiede mese e giorno nulli.")
    if precision=="MONTH" and (m is None or day is not None):raise HTTPException(422,"MONTH richiede mese e giorno nullo.")
    try:evdate=date(y,m,day) if precision=="DAY" else None
    except (TypeError,ValueError) as e:raise HTTPException(422,"Data evento non valida.") from e
    if "event_type" in d:d["event_type"]=str(d["event_type"]).upper()
    if "date_precision" in d:d["date_precision"]=precision
    if "event_year" in d or "event_month" in d or "event_day" in d or "date_precision" in d:d["event_date"]=evdate
    if "country_code" in d and d["country_code"]:d["country_code"]=d["country_code"].upper()
    if "title" in d:d["title"]=str(d["title"]).strip()
    if d.get("event_type",old["event_type"]) not in TYPES or d.get("status",old["status"]) not in STATUSES:raise HTTPException(422,"Tipo o stato evento non valido.")
    params={"id":rid};sets=[]
    for k,v in d.items():
        cast={"event_type":"event_type","date_precision":"date_precision","status":"verification_status"}.get(k)
        sets.append(f"{k}=CAST(:{k} AS {cast})" if cast else f"{k}=:{k}");params[k]=v
    try:
        if sets:db.execute(text("UPDATE events SET "+",".join(sets)+" WHERE id=:id"),params)
        if artists is not None:
            db.execute(text("DELETE FROM event_artists WHERE event_id=:id"),{"id":rid})
            for a in artists:
                aid=a.get("artist_id")
                if not db.execute(text("SELECT id FROM artists WHERE id=:id"),{"id":aid}).scalar_one_or_none():raise HTTPException(422,"Artista associato non esistente.")
                db.execute(text("INSERT INTO event_artists(event_id,artist_id,role) VALUES (:e,:a,:r) ON CONFLICT DO NOTHING"),{"e":rid,"a":aid,"r":a.get("role","PARTICIPANT")})
        db.commit();return event_detail(db,rid)
    except IntegrityError as e:db.rollback();raise HTTPException(422,"Venue o riferimento evento non valido.") from e

@router.delete("/events/{rid}",status_code=204)
def delete_event(rid:UUID,db:Session=Depends(get_db)):
    x=db.execute(text("DELETE FROM events WHERE id=:id"),{"id":rid})
    if not x.rowcount:db.rollback();raise HTTPException(404,"Evento non trovato.")
    db.commit();return Response(status_code=204)

