from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import get_db

router=APIRouter(tags=["catalog"])

def row(db,sql,p=None):
    x=db.execute(text(sql),p or {}).mappings().first()
    return dict(x) if x else None

def get_or_404(db,table,rid):
    if table not in {"labels","release_groups","releases"}: raise ValueError()
    x=row(db,f"SELECT * FROM {table} WHERE id=:id",{"id":rid})
    if not x: raise HTTPException(404,f"Record {table} non trovato.")
    return x

def validate_ids(db,table,values):
    if table not in {"artists","genres"}: raise ValueError()
    vals=list(dict.fromkeys(values or []))
    found=db.execute(text(f"SELECT id FROM {table} WHERE id=ANY(:ids)"),{"ids":vals}).scalars().all() if vals else []
    if len(found)!=len(vals): raise HTTPException(422,f"Uno o più riferimenti {table} non esistono.")
    return vals

def partial_date(y,m,d,p):
    p=(p or "").upper()
    if p not in {"YEAR","MONTH","DAY"} or y is None: raise HTTPException(422,"Precisione o anno non validi.")
    if p=="YEAR" and (m is not None or d is not None): raise HTTPException(422,"YEAR richiede mese e giorno nulli.")
    if p=="MONTH" and (m is None or d is not None): raise HTTPException(422,"MONTH richiede mese e giorno nullo.")
    if p=="DAY":
        try: date(y,m,d)
        except (TypeError,ValueError) as e: raise HTTPException(422,"Data non valida.") from e

@router.get("/labels")
def labels(q:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    return [dict(x) for x in db.execute(text("SELECT * FROM labels WHERE (:q IS NULL OR name ILIKE '%'||:q||'%') ORDER BY lower(name),id OFFSET :o LIMIT :n"),{"q":q,"o":offset,"n":limit}).mappings().all()]

@router.post("/labels",status_code=201)
def create_label(p:dict,db:Session=Depends(get_db)):
    name=str(p.get("name","")).strip()
    if not name: raise HTTPException(422,"name obbligatorio.")
    d={"name":name,"country_code":(p.get("country_code") or "").upper() or None,"founded_year":p.get("founded_year"),"dissolved_year":p.get("dissolved_year"),"website":p.get("website")}
    if d["founded_year"] and d["dissolved_year"] and d["dissolved_year"]<d["founded_year"]: raise HTTPException(422,"Intervallo anni etichetta non valido.")
    try:
        x=row(db,"INSERT INTO labels(name,country_code,founded_year,dissolved_year,website) VALUES (:name,:country_code,:founded_year,:dissolved_year,:website) RETURNING *",d);db.commit();return x
    except IntegrityError as e:db.rollback();raise HTTPException(409,"Etichetta già presente.") from e

@router.get("/labels/{rid}")
def label(rid:UUID,db:Session=Depends(get_db)):return get_or_404(db,"labels",rid)

@router.patch("/labels/{rid}")
def patch_label(rid:UUID,p:dict,db:Session=Depends(get_db)):
    old=get_or_404(db,"labels",rid);allowed={"name","country_code","founded_year","dissolved_year","website"};d={k:v for k,v in p.items() if k in allowed}
    if not d:return old
    if "name" in d:
        if not isinstance(d["name"],str) or not d["name"].strip():raise HTTPException(422,"name non valido.")
        d["name"]=d["name"].strip()
    if d.get("country_code"):d["country_code"]=d["country_code"].upper()
    merged={**old,**d}
    if merged["founded_year"] and merged["dissolved_year"] and merged["dissolved_year"]<merged["founded_year"]:raise HTTPException(422,"Intervallo anni etichetta non valido.")
    try:
        x=row(db,"UPDATE labels SET "+",".join(f"{k}=:{k}" for k in d)+" WHERE id=:id RETURNING *",{**d,"id":rid});db.commit();return x
    except IntegrityError as e:db.rollback();raise HTTPException(409,"Etichetta già presente.") from e

@router.delete("/labels/{rid}",status_code=204)
def delete_label(rid:UUID,db:Session=Depends(get_db)):
    x=db.execute(text("DELETE FROM labels WHERE id=:id"),{"id":rid})
    if not x.rowcount:db.rollback();raise HTTPException(404,"Etichetta non trovata.")
    db.commit();return Response(status_code=204)

@router.get("/release-groups")
def release_groups(q:str|None=None,primary_type:str|None=None,year:int|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    xs=db.execute(text("""SELECT g.*,COUNT(DISTINCT r.id)::int edition_count FROM release_groups g LEFT JOIN releases r ON r.release_group_id=g.id
      WHERE (:q IS NULL OR g.title ILIKE '%'||:q||'%') AND (:t IS NULL OR g.primary_type=:t) AND (:y IS NULL OR g.first_release_year=:y)
      GROUP BY g.id ORDER BY g.first_release_year NULLS LAST,lower(g.title),g.id OFFSET :o LIMIT :n"""),{"q":q,"t":primary_type,"y":year,"o":offset,"n":limit}).mappings().all()
    return [dict(x) for x in xs]

@router.post("/release-groups",status_code=201)
def create_release_group(p:dict,db:Session=Depends(get_db)):
    title=str(p.get("title","")).strip();kind=str(p.get("primary_type","")).strip().upper()
    if not title or not kind:raise HTTPException(422,"title e primary_type sono obbligatori.")
    x=row(db,"INSERT INTO release_groups(title,primary_type,secondary_type,first_release_year,description) VALUES (:title,:kind,:secondary,:year,:description) RETURNING *",{"title":title,"kind":kind,"secondary":p.get("secondary_type"),"year":p.get("first_release_year"),"description":p.get("description")});db.commit();return x

@router.get("/release-groups/{rid}")
def release_group(rid:UUID,db:Session=Depends(get_db)):
    x=get_or_404(db,"release_groups",rid)
    x["releases"]=[dict(r) for r in db.execute(text("SELECT id,title,country_code,release_year,release_month,release_day,date_precision,format,status FROM releases WHERE release_group_id=:id ORDER BY release_year,release_month,release_day"),{"id":rid}).mappings().all()]
    return x

@router.patch("/release-groups/{rid}")
def patch_release_group(rid:UUID,p:dict,db:Session=Depends(get_db)):
    get_or_404(db,"release_groups",rid);allowed={"title","primary_type","secondary_type","first_release_year","description"};d={k:v for k,v in p.items() if k in allowed}
    if not d:return release_group(rid,db)
    if "title" in d:d["title"]=str(d["title"]).strip()
    if "primary_type" in d:d["primary_type"]=str(d["primary_type"]).upper()
    x=row(db,"UPDATE release_groups SET "+",".join(f"{k}=:{k}" for k in d)+" WHERE id=:id RETURNING *",{**d,"id":rid});db.commit();return x

@router.delete("/release-groups/{rid}",status_code=204)
def delete_release_group(rid:UUID,db:Session=Depends(get_db)):
    x=db.execute(text("DELETE FROM release_groups WHERE id=:id"),{"id":rid})
    if not x.rowcount:db.rollback();raise HTTPException(404,"Release group non trovato.")
    db.commit();return Response(status_code=204)

def release_detail(db,rid):
    x=row(db,"""SELECT r.*,g.title release_group_title,l.name label_name FROM releases r
      LEFT JOIN release_groups g ON g.id=r.release_group_id LEFT JOIN labels l ON l.id=r.label_id WHERE r.id=:id""",{"id":rid})
    if not x:raise HTTPException(404,"Pubblicazione non trovata.")
    x["artists"]=[dict(a) for a in db.execute(text("SELECT a.id,a.canonical_name,ra.credited_as,ra.credit_role,ra.position FROM release_artists ra JOIN artists a ON a.id=ra.artist_id WHERE ra.release_id=:id ORDER BY ra.position NULLS LAST,a.canonical_name"),{"id":rid}).mappings().all()]
    x["genres"]=[dict(g) for g in db.execute(text("SELECT g.id,g.name FROM release_genres rg JOIN genres g ON g.id=rg.genre_id WHERE rg.release_id=:id ORDER BY g.name"),{"id":rid}).mappings().all()]
    return x

@router.get("/releases")
def releases(q:str|None=None,artist_id:UUID|None=None,release_group_id:UUID|None=None,year:int|None=None,country_code:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    xs=db.execute(text("""SELECT r.id,r.release_group_id,r.title,r.country_code,r.release_year,r.release_month,r.release_day,r.date_precision,r.format,r.catalog_number,r.status,g.title release_group_title,l.name label_name
      FROM releases r LEFT JOIN release_groups g ON g.id=r.release_group_id LEFT JOIN labels l ON l.id=r.label_id
      WHERE (:q IS NULL OR r.title ILIKE '%'||:q||'%') AND (:a IS NULL OR EXISTS(SELECT 1 FROM release_artists x WHERE x.release_id=r.id AND x.artist_id=:a))
      AND (:g IS NULL OR r.release_group_id=:g) AND (:y IS NULL OR r.release_year=:y) AND (:c IS NULL OR r.country_code=:c)
      ORDER BY r.release_year NULLS LAST,r.release_month NULLS LAST,r.release_day NULLS LAST,lower(r.title) OFFSET :o LIMIT :n"""),
      {"q":q,"a":artist_id,"g":release_group_id,"y":year,"c":country_code.upper() if country_code else None,"o":offset,"n":limit}).mappings().all()
    return [dict(x) for x in xs]

@router.post("/releases",status_code=201)
def create_release(p:dict,db:Session=Depends(get_db)):
    title=str(p.get("title","")).strip();y=p.get("release_year");m=p.get("release_month");d=p.get("release_day");precision=str(p.get("date_precision","YEAR")).upper()
    if not title:raise HTTPException(422,"title obbligatorio.")
    partial_date(y,m,d,precision)
    status_value=str(p.get("status","TO_VERIFY")).upper()
    if status_value not in {"VERIFIED","CONFIRMED","PRELIMINARY","TO_VERIFY","UNCERTAIN"}:raise HTTPException(422,"status non valido.")
    artists=validate_ids(db,"artists",p.get("artist_ids",[]));genres=validate_ids(db,"genres",p.get("genre_ids",[]))
    data={"group":p.get("release_group_id"),"title":title,"country":(p.get("country_code") or "").upper() or None,"release_date":date(y,m,d) if precision=="DAY" else None,"year":y,"month":m,"day":d,"precision":precision,"label":p.get("label_id"),"catalog":p.get("catalog_number"),"format":p.get("format"),"barcode":p.get("barcode"),"status":status_value,"notes":p.get("notes")}
    try:
        x=row(db,"""INSERT INTO releases(release_group_id,title,country_code,release_date,release_year,release_month,release_day,date_precision,label_id,catalog_number,format,barcode,status,notes)
          VALUES (:group,:title,:country,:release_date,:year,:month,:day,CAST(:precision AS date_precision),:label,:catalog,:format,:barcode,CAST(:status AS verification_status),:notes) RETURNING id""",data);rid=x["id"]
        for pos,aid in enumerate(artists,1):db.execute(text("INSERT INTO release_artists(release_id,artist_id,credit_role,position) VALUES (:r,:a,'PRIMARY',:p)"),{"r":rid,"a":aid,"p":pos})
        for gid in genres:db.execute(text("INSERT INTO release_genres(release_id,genre_id) VALUES (:r,:g)"),{"r":rid,"g":gid})
        db.commit();return release_detail(db,rid)
    except IntegrityError as e:db.rollback();raise HTTPException(422,"Release group o label non validi.") from e

@router.get("/releases/{rid}")
def get_release(rid:UUID,db:Session=Depends(get_db)):return release_detail(db,rid)

@router.patch("/releases/{rid}")
def patch_release(rid:UUID,p:dict,db:Session=Depends(get_db)):
    old=release_detail(db,rid);allowed={"release_group_id","title","country_code","release_year","release_month","release_day","date_precision","label_id","catalog_number","format","barcode","status","notes"}
    d={k:v for k,v in p.items() if k in allowed};artists=p.get("artist_ids");genres=p.get("genre_ids")
    if not d and artists is None and genres is None:return old
    merged={**old,**d};precision=str(merged.get("date_precision","YEAR")).upper()
    partial_date(merged.get("release_year"),merged.get("release_month"),merged.get("release_day"),precision)
    if "title" in d:d["title"]=str(d["title"]).strip()
    if "country_code" in d:d["country_code"]=d["country_code"].upper() if d["country_code"] else None
    if any(k in d for k in ("release_year","release_month","release_day","date_precision")):d["release_date"]=date(merged["release_year"],merged["release_month"],merged["release_day"]) if precision=="DAY" else None
    if "date_precision" in d:d["date_precision"]=precision
    if "status" in d:d["status"]=d["status"].upper()
    sets=[];params={"id":rid}
    for k,v in d.items():
        if k=="date_precision":sets.append("date_precision=CAST(:date_precision AS date_precision)")
        elif k=="status":sets.append("status=CAST(:status AS verification_status)")
        else:sets.append(f"{k}=:{k}")
        params[k]=v
    try:
        if sets:db.execute(text("UPDATE releases SET "+",".join(sets)+" WHERE id=:id"),params)
        if artists is not None:
            vals=validate_ids(db,"artists",artists);db.execute(text("DELETE FROM release_artists WHERE release_id=:id"),{"id":rid})
            for pos,aid in enumerate(vals,1):db.execute(text("INSERT INTO release_artists(release_id,artist_id,credit_role,position) VALUES (:r,:a,'PRIMARY',:p)"),{"r":rid,"a":aid,"p":pos})
        if genres is not None:
            vals=validate_ids(db,"genres",genres);db.execute(text("DELETE FROM release_genres WHERE release_id=:id"),{"id":rid})
            for gid in vals:db.execute(text("INSERT INTO release_genres(release_id,genre_id) VALUES (:r,:g)"),{"r":rid,"g":gid})
        db.commit();return release_detail(db,rid)
    except IntegrityError as e:db.rollback();raise HTTPException(422,"Riferimento o associazione non valido.") from e

@router.delete("/releases/{rid}",status_code=204)
def delete_release(rid:UUID,db:Session=Depends(get_db)):
    x=db.execute(text("DELETE FROM releases WHERE id=:id"),{"id":rid})
    if not x.rowcount:db.rollback();raise HTTPException(404,"Pubblicazione non trovata.")
    db.commit();return Response(status_code=204)
